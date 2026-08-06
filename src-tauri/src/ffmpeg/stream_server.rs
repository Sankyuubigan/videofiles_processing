use std::io::SeekFrom;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};
use std::sync::mpsc;
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncSeekExt, AsyncWriteExt};
use tokio::net::TcpStream;

use crate::ffmpeg::preview::preview_root;

#[derive(Clone)]
pub struct StreamState {
    pub port: u16,
}

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const MAX_HEAD_SIZE: usize = 64 * 1024;

#[derive(Default)]
struct Headers {
    range: Option<String>,
    origin: Option<String>,
}

pub fn start_stream_server() -> u16 {
    let (port_tx, port_rx) = mpsc::channel::<u16>();

    std::thread::spawn(move || {
        let result = catch_unwind(AssertUnwindSafe(|| {
            let rt = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .expect("Failed to create tokio runtime for stream server");

            rt.block_on(async move {
                let listener = match tokio::net::TcpListener::bind(("127.0.0.1", 0)).await {
                    Ok(l) => l,
                    Err(e) => {
                        log::error!("Stream server failed to bind: {}", e);
                        let _ = port_tx.send(0);
                        return;
                    }
                };
                let port = match listener.local_addr() {
                    Ok(addr) => addr.port(),
                    Err(e) => {
                        log::error!("Failed to get stream server port: {}", e);
                        let _ = port_tx.send(0);
                        return;
                    }
                };
                let _ = port_tx.send(port);

                let state = StreamState { port };
                server_loop(listener, state).await;
            });
        }));
        if let Err(e) = result {
            let msg = if let Some(s) = e.downcast_ref::<String>() {
                s.clone()
            } else if let Some(s) = e.downcast_ref::<&str>() {
                s.to_string()
            } else {
                "unknown panic".to_string()
            };
            log::error!("Stream server thread panicked: {}", msg);
        }
    });

    let port = port_rx
        .recv_timeout(Duration::from_secs(5))
        .unwrap_or(0);
    log::info!("Video stream server started on port {}", port);
    port
}

async fn server_loop(listener: tokio::net::TcpListener, state: StreamState) {
    let port = state.port;
    loop {
        match listener.accept().await {
            Ok((stream, _peer)) => {
                let port = port;
                tokio::spawn(handle_conn(stream, port));
            }
            Err(e) => {
                log::error!("Stream server accept error: {}", e);
            }
        }
    }
}

async fn handle_conn(mut stream: TcpStream, port: u16) {
    let head = match tokio::time::timeout(READ_TIMEOUT, read_http_head(&mut stream)).await {
        Ok(Ok(head)) => head,
        Ok(Err(e)) => {
            log::debug!("Stream connection read error: {}", e);
            return;
        }
        Err(_) => {
            log::warn!("Stream connection read timeout");
            return;
        }
    };

    let head_str = match String::from_utf8(head) {
        Ok(s) => s,
        Err(_) => {
            let _ = StreamSimple::new(&mut stream, 400, "Bad Request", None, None).await;
            return;
        }
    };

    let mut lines = head_str.split("\r\n");
    let request_line = lines.next().unwrap_or("");
    let mut parts = request_line.split(' ');
    let method = parts.next().unwrap_or("").to_ascii_uppercase();
    let target_raw = parts.next().unwrap_or("");

    let target = match target_raw.find("//") {
        Some(idx) if target_raw[..idx].starts_with("http") => {
            let after = &target_raw[idx + 2..];
            match after.find('/') {
                Some(rest) => &after[rest..],
                None => "/",
            }
        }
        _ => target_raw,
    }
    .to_string();

    let headers = Headers {
        range: header_value(&head_str, "range"),
        origin: header_value(&head_str, "origin"),
    };

    if method == "OPTIONS" {
        respond_options(&mut stream).await;
        return;
    }

    if method != "GET" && method != "HEAD" {
        let _ = StreamSimple::new(&mut stream, 405, "Method Not Allowed", None, headers.origin.as_deref()).await;
        return;
    }

    let (route, raw_path) = match parse_target(&target) {
        Some(r) => r,
        None => {
            let _ = StreamSimple::new(&mut stream, 400, "Bad Request", None, headers.origin.as_deref()).await;
            return;
        }
    };

    let path = match percent_decode(&raw_path) {
        Some(p) => p,
        None => {
            let _ = StreamSimple::new(&mut stream, 400, "Bad Request", None, headers.origin.as_deref()).await;
            return;
        }
    };

    log::debug!("Stream {} request: {}", route_label(route), path);

    let is_head = method == "HEAD";
    match route {
        Route::Video | Route::Cache => {
            let _ = serve_file(&mut stream, &path, &headers, is_head, port).await;
        }
        Route::Preview => {
            let requested = PathBuf::from(&path);
            let root = preview_root();

            let resolved = match requested.canonicalize() {
                Ok(p) => p,
                Err(_) => {
                    log::error!("Preview: failed to resolve path: {}", path);
                    let _ = StreamSimple::new(&mut stream, 404, "Not Found", None, headers.origin.as_deref()).await;
                    return;
                }
            };

            let allowed = match root.canonicalize() {
                Ok(r) => r,
                Err(_) => {
                    log::error!("Preview: preview root not found: {}", root.display());
                    let _ = StreamSimple::new(&mut stream, 500, "Internal Server Error", None, headers.origin.as_deref()).await;
                    return;
                }
            };

            if !resolved.starts_with(&allowed) {
                log::error!("Preview: path outside preview root: {}", resolved.display());
                let _ = StreamSimple::new(&mut stream, 403, "Forbidden", None, headers.origin.as_deref()).await;
                return;
            }

            let _ = serve_file(&mut stream, &resolved.to_string_lossy(), &headers, is_head, port).await;
        }
    }
}

// ---- routing helpers ----

#[derive(Clone, Copy, PartialEq)]
enum Route {
    Video,
    Preview,
    Cache,
}

fn route_label(route: Route) -> &'static str {
    match route {
        Route::Video => "/video",
        Route::Preview => "/preview",
        Route::Cache => "/cache",
    }
}

fn parse_target(target: &str) -> Option<(Route, &str)> {
    for (prefix, route) in [
        ("/cache/", Route::Cache),
        ("/video?path=", Route::Video),
        ("/preview?path=", Route::Preview),
    ] {
        if let Some(rest) = target.strip_prefix(prefix) {
            return Some((route, rest));
        }
    }
    None
}

fn header_value(head: &str, name: &str) -> Option<String> {
    for line in head.lines() {
        if let Some((k, v)) = line.split_once(':') {
            if k.trim().eq_ignore_ascii_case(name) {
                return Some(v.trim().to_string());
            }
        }
    }
    None
}

fn percent_decode(s: &str) -> Option<String> {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hi = (bytes[i + 1] as char).to_digit(16)?;
            let lo = (bytes[i + 2] as char).to_digit(16)?;
            out.push((hi * 16 + lo) as u8);
            i += 3;
        } else {
            out.push(bytes[i]);
            i += 1;
        }
    }
    String::from_utf8(out).ok()
}

// ---- response writing --------------------------------------------------

struct StreamSimple;

impl StreamSimple {
    async fn new(
        stream: &mut TcpStream,
        code: u16,
        reason: &str,
        body: Option<&str>,
        _origin: Option<&str>,
    ) -> std::io::Result<()> {
        let body = body.unwrap_or("");
        let status = status_line(code, reason);
        let resp = format!(
            "{}\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n{}",
            status,
            body.len(),
            body
        );
        stream.write_all(resp.as_bytes()).await?;
        stream.flush().await?;
        let _ = stream.shutdown().await;
        Ok(())
    }
}

async fn respond_options(stream: &mut TcpStream) {
    let resp = concat!(
        "HTTP/1.1 204 No Content\r\n",
        "Access-Control-Allow-Origin: *\r\n",
        "Access-Control-Allow-Private-Network: true\r\n",
        "Access-Control-Allow-Methods: GET, HEAD, OPTIONS\r\n",
        "Access-Control-Allow-Headers: *\r\n",
        "Access-Control-Max-Age: 86400\r\n",
        "Content-Length: 0\r\n",
        "Connection: close\r\n\r\n",
    );
    if stream.write_all(resp.as_bytes()).await.is_ok() {
        let _ = stream.flush().await;
    }
    let _ = stream.shutdown().await;
}

fn status_line(code: u16, reason: &str) -> String {
    format!("HTTP/1.1 {} {}", code, reason)
}

fn mime_from_path(path: &str) -> &'static str {
    let lower = path.to_lowercase();
    if lower.ends_with(".mp4") || lower.ends_with(".m4v") {
        "video/mp4"
    } else if lower.ends_with(".webm") {
        "video/webm"
    } else if lower.ends_with(".mkv") || lower.ends_with(".matroska") {
        "video/x-matroska"
    } else if lower.ends_with(".avi") {
        "video/x-msvideo"
    } else if lower.ends_with(".mov") {
        "video/quicktime"
    } else if lower.ends_with(".ogg") || lower.ends_with(".ogv") {
        "video/ogg"
    } else if lower.ends_with(".ts") {
        "video/mp2t"
    } else if lower.ends_with(".m3u8") {
        "application/vnd.apple.mpegurl"
    } else {
        "application/octet-stream"
    }
}

fn parse_range(header: &str, file_size: u64) -> Option<(u64, u64)> {
    let header = header.trim();
    if let Some(range) = header.strip_prefix("bytes=") {
        let parts: Vec<&str> = range.split('-').collect();
        if parts.len() == 2 {
            let start = parts[0].parse::<u64>().ok()?;
            let end = if parts[1].is_empty() {
                file_size - 1
            } else {
                parts[1].parse::<u64>().ok()?
            };
            if start <= end && start < file_size {
                return Some((start, end.min(file_size - 1)));
            }
        }
    }
    None
}

async fn serve_file(
    stream: &mut TcpStream,
    file_path: &str,
    headers: &Headers,
    is_head: bool,
    port: u16,
) -> std::io::Result<()> {
    if !Path::new(file_path).exists() {
        log::debug!("Stream: file not found: {}", file_path);
        StreamSimple::new(stream, 404, "Not Found", Some("Not Found"), headers.origin.as_deref()).await?;
        return Ok(());
    }

    if file_path.to_lowercase().ends_with(".m3u8") {
        return serve_playlist(stream, file_path, headers, is_head, port).await;
    }

    let mut file = match tokio::fs::File::open(file_path).await {
        Ok(f) => f,
        Err(e) => {
            log::error!("Stream: failed to open {}: {}", file_path, e);
            StreamSimple::new(stream, 500, "Internal Server Error", None, headers.origin.as_deref()).await?;
            return Ok(());
        }
    };

    let metadata = match file.metadata().await {
        Ok(m) => m,
        Err(_) => {
            StreamSimple::new(stream, 500, "Internal Server Error", None, headers.origin.as_deref()).await?;
            return Ok(());
        }
    };
    let file_size = metadata.len();
    let mime = mime_from_path(file_path);

    let range = headers.range.as_deref().and_then(|r| parse_range(r, file_size));

    let (status_line, content_len, content_range) = match range {
        Some((start, end)) => {
            file.seek(SeekFrom::Start(start)).await.map_err(|_| {
                std::io::Error::new(std::io::ErrorKind::Other, "seek failed")
            })?;
            (
                "HTTP/1.1 206 Partial Content".to_string(),
                (end - start + 1).to_string(),
                Some(format!("bytes {}-{}/{}", start, end, file_size)),
            )
        }
        None => (
            "HTTP/1.1 200 OK".to_string(),
            file_size.to_string(),
            None,
        ),
    };

    let mut header = String::new();
    header.push_str(&status_line);
    header.push_str("\r\n");
    header.push_str("Content-Type: ");
    header.push_str(mime);
    header.push_str("\r\n");
    header.push_str("Accept-Ranges: bytes\r\n");
    header.push_str("Access-Control-Allow-Origin: *\r\n");
    header.push_str("Cache-Control: no-store\r\n");
    header.push_str("Content-Length: ");
    header.push_str(&content_len);
    header.push_str("\r\n");
    if let Some(cr) = content_range {
        header.push_str("Content-Range: ");
        header.push_str(&cr);
        header.push_str("\r\n");
    }
    header.push_str("Connection: close\r\n\r\n");

    if stream.write_all(header.as_bytes()).await.is_err() {
        return Ok(());
    }

    if !is_head {
        match range {
            Some((start, end)) => {
                let length = end - start + 1;
                let mut limited = file.take(length);
                let _ = tokio::io::copy(&mut limited, stream).await;
            }
            None => {
                let _ = tokio::io::copy(&mut file, stream).await;
            }
        }
    }

    let _ = stream.flush().await;
    let _ = stream.shutdown().await;
    Ok(())
}

async fn serve_playlist(
    stream: &mut TcpStream,
    file_path: &str,
    headers: &Headers,
    is_head: bool,
    port: u16,
) -> std::io::Result<()> {
    let content = match tokio::fs::read(file_path).await {
        Ok(c) => c,
        Err(e) => {
            log::error!("Stream: failed to read playlist {}: {}", file_path, e);
            StreamSimple::new(stream, 500, "Internal Server Error", None, headers.origin.as_deref()).await?;
            return Ok(());
        }
    };

    let text = String::from_utf8_lossy(&content);
    let rewritten = rewrite_playlist(&text, file_path, port);

    let mut resp = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: application/vnd.apple.mpegurl\r\nAccess-Control-Allow-Origin: *\r\nCache-Control: no-store\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        rewritten.len()
    );
    if !is_head {
        resp.push_str(&rewritten);
    }

    if stream.write_all(resp.as_bytes()).await.is_err() {
        return Ok(());
    }
    let _ = stream.flush().await;
    let _ = stream.shutdown().await;
    Ok(())
}

fn rewrite_playlist(text: &str, playlist_path: &str, port: u16) -> String {
    let dir = Path::new(playlist_path)
        .parent()
        .unwrap_or(Path::new("."));
    let mut out = String::with_capacity(text.len() * 2);
    for raw in text.lines() {
        let line = raw.trim_end_matches('\r');
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with("http://") || trimmed.starts_with("https://") {
            out.push_str(line);
            out.push('\n');
            continue;
        }
        let seg_abs = dir.join(trimmed);
        let seg_path = seg_abs.to_string_lossy().to_string();
        out.push_str(&format!(
            "http://127.0.0.1:{}/preview?path={}",
            port,
            percent_encode(&seg_path)
        ));
        out.push('\n');
    }
    out
}

fn percent_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        if b.is_ascii_alphanumeric() || b == b'-' || b == b'_' || b == b'.' || b == b'~' {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{:02X}", b));
        }
    }
    out
}

// ---- http head reader ----------------------------------------------------

async fn read_http_head(stream: &mut TcpStream) -> std::io::Result<Vec<u8>> {
    let mut buf = Vec::with_capacity(4096);
    let mut chunk = [0u8; 4096];
    loop {
        let n = stream.read(&mut chunk).await?;
        if n == 0 {
            return Ok(buf);
        }
        buf.extend_from_slice(&chunk[..n]);
        if buf.len() > MAX_HEAD_SIZE {
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "headers too large"));
        }
        if buf.windows(4).any(|w| w == b"\r\n\r\n") {
            return Ok(buf);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::{Read, Write};
    use std::net::TcpStream;

    fn http_raw(port: u16, request: &str) -> String {
        let mut stream =
            TcpStream::connect(("127.0.0.1", port)).expect("connect to stream server");
        stream.write_all(request.as_bytes()).expect("write request");
        stream.shutdown(std::net::Shutdown::Write).expect("shutdown write");
        let mut buf = Vec::new();
        stream.read_to_end(&mut buf).expect("read response");
        String::from_utf8_lossy(&buf).to_string()
    }

    fn first_line(resp: &str) -> &str {
        resp.lines().next().unwrap_or("")
    }

    fn header<'a>(resp: &'a str, name: &str) -> Option<&'a str> {
        resp.lines().find_map(|l| {
            let s = l.trim_end_matches('\r');
            s.split_once(':')
                .filter(|(k, _)| k.eq_ignore_ascii_case(name))
                .map(|(_, v)| v.trim())
        })
    }

    #[test]
    fn video_range_returns_206_with_cors() {
        let dir = std::env::temp_dir().join("videofile_pro_stream_test");
        fs::create_dir_all(&dir).unwrap();
        let file = dir.join("sample.mp4");
        let data: Vec<u8> = (0..4096u32).map(|i| (i % 251) as u8).collect();
        fs::write(&file, &data).unwrap();

        let port = start_stream_server();
        let url = format!("http://127.0.0.1:{}/video?path={}",
            port, file.to_string_lossy().replace('\\', "/"));
        let resp = http_raw(port, &format!(
            "GET {} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nRange: bytes=0-99\r\nConnection: close\r\n\r\n",
            url, port));

        assert!(first_line(&resp).contains("206"), "got: {}", first_line(&resp));
        assert_eq!(header(&resp, "Content-Type"), Some("video/mp4"));
        assert_eq!(header(&resp, "Access-Control-Allow-Origin"), Some("*"));
        assert_eq!(header(&resp, "Content-Range").map(|r| r.starts_with("bytes 0-99/4096")), Some(true));
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn video_without_range_returns_200() {
        let dir = std::env::temp_dir().join("videofile_pro_stream_test2");
        fs::create_dir_all(&dir).unwrap();
        let file = dir.join("clip.mkv");
        fs::write(&file, vec![0u8; 512]).unwrap();

        let port = start_stream_server();
        let url = format!("http://127.0.0.1:{}/video?path={}",
            port, file.to_string_lossy().replace('\\', "/"));

        let resp = http_raw(port, &format!(
            "GET {} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n\r\n",
            url, port));
        assert!(resp.contains("200 OK"), "got status: {}", first_line(&resp));
        assert_eq!(header(&resp, "Content-Type"), Some("video/x-matroska"));
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn options_preview_returns_private_network_preflight() {
        let port = start_stream_server();
        let resp = http_raw(port, &format!(
            "OPTIONS /preview?path=x HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://tauri.localhost\r\nAccess-Control-Request-Private-Network: true\r\nConnection: close\r\n\r\n",
            port));
        assert!(first_line(&resp).contains("204"), "got: {}", first_line(&resp));
        assert_eq!(header(&resp, "Access-Control-Allow-Origin"), Some("*"));
        assert_eq!(header(&resp, "Access-Control-Allow-Private-Network"), Some("true"));
        assert_eq!(header(&resp, "Access-Control-Max-Age"), Some("86400"));
    }

    #[test]
    fn video_missing_file_returns_404() {
        let port = start_stream_server();
        let url = format!("http://127.0.0.1:{}/video?path={}", port, "%2Fnonexistent%2Fmissing.mp4");
        let resp = http_raw(port, &format!(
            "GET {} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n\r\n",
            url, port));
        assert!(first_line(&resp).contains("404"), "got: {}", first_line(&resp));
    }

    #[test]
    fn cache_route_serves_absolute_path() {
        let dir = std::env::temp_dir().join("videofile_pro_stream_test4");
        fs::create_dir_all(&dir).unwrap();
        let file = dir.join("index.m3u8");
        fs::write(&file, "#EXTM3U\n#EXTINF:2.000000,\nseg_00000.ts\n").unwrap();

        let port = start_stream_server();
        let enc = { let p = file.to_string_lossy().replace('\\', "/"); let mut s = String::new(); for b in p.bytes() { if b.is_ascii_alphanumeric() || b == b'/' || b == b'.' || b == b'-' || b == b'_' { s.push(b as char); } else { s.push_str(&format!("%{:02X}", b)); } } s };
        let resp = http_raw(port, &format!(
            "GET /cache/{} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n\r\n",
            enc, port));
        assert!(first_line(&resp).contains("200"), "got: {}", first_line(&resp));
        assert_eq!(header(&resp, "Content-Type"), Some("application/vnd.apple.mpegurl"));
        assert!(
            resp.contains(&format!("http://127.0.0.1:{}/preview?path=", port)),
            "playlist must embed absolute segment URLs, got: {}",
            resp.lines().find(|l| l.contains("seg_")).unwrap_or("")
        );
        assert!(!resp.contains("\nseg_00000.ts"), "relative segment not rewritten");
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn head_request_returns_headers_no_body() {
        let dir = std::env::temp_dir().join("videofile_pro_stream_test3");
        fs::create_dir_all(&dir).unwrap();
        let file = dir.join("clip.webm");
        fs::write(&file, vec![1u8; 300]).unwrap();

        let port = start_stream_server();
        let url = format!("http://127.0.0.1:{}/video?path={}",
            port, file.to_string_lossy().replace('\\', "/"));
        let resp = http_raw(port, &format!(
            "HEAD {} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n\r\n",
            url, port));
        assert!(first_line(&resp).contains("200"), "got: {}", first_line(&resp));
        assert_eq!(header(&resp, "Content-Type"), Some("video/webm"));
        assert_eq!(header(&resp, "Content-Length"), Some("300"));
        fs::remove_dir_all(&dir).ok();
    }
}