use std::io::SeekFrom;
use std::net::TcpListener;
use std::path::Path;
use axum::{
    Router,
    extract::{Query, State},
    http::{HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
};
use serde::Deserialize;
use tokio::io::{AsyncReadExt, AsyncSeekExt};
use tokio::net::TcpListener as TokioTcpListener;

#[derive(Clone)]
pub struct StreamState {
    pub port: u16,
}

#[derive(Deserialize)]
pub struct VideoQuery {
    pub path: String,
}

pub fn start_stream_server() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("Failed to bind random port");
    let port = match listener.local_addr() {
        Ok(addr) => addr.port(),
        Err(e) => {
            log::error!("Failed to get stream server port: {}", e);
            0
        }
    };

    std::thread::spawn(move || {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("Failed to create tokio runtime for stream server");

        let tokio_listener = TokioTcpListener::from_std(listener)
            .expect("Failed to convert to tokio listener");

        let state = StreamState { port };

        let app = Router::new()
            .route("/video", axum::routing::get(handle_video))
            .with_state(state);

        rt.block_on(async move {
            axum::serve(tokio_listener, app)
                .await
                .expect("Stream server failed");
        });
    });

    log::info!("Video stream server started on port {}", port);
    port
}

fn mime_from_path(path: &str) -> &str {
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

async fn handle_video(
    State(_state): State<StreamState>,
    Query(query): Query<VideoQuery>,
    headers: HeaderMap,
) -> Result<Response, StatusCode> {
    let file_path = query.path;

    if !Path::new(&file_path).exists() {
        log::error!("Stream: file not found: {}", file_path);
        return Err(StatusCode::NOT_FOUND);
    }

    let mut file = tokio::fs::File::open(&file_path)
        .await
        .map_err(|e| {
            log::error!("Stream: failed to open {}: {}", file_path, e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let metadata = file.metadata().await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let file_size = metadata.len();
    let mime = mime_from_path(&file_path);

    let mut response_headers = HeaderMap::new();
    response_headers.insert(
        axum::http::header::CONTENT_TYPE,
        HeaderValue::from_str(mime).unwrap_or_else(|_| HeaderValue::from_static("application/octet-stream")),
    );
    response_headers.insert(
        axum::http::header::ACCEPT_RANGES,
        HeaderValue::from_static("bytes"),
    );
    response_headers.insert(
        axum::http::header::ACCESS_CONTROL_ALLOW_ORIGIN,
        HeaderValue::from_static("*"),
    );

    if let Some(range_header) = headers.get(axum::http::header::RANGE) {
        if let Ok(range_str) = range_header.to_str() {
            if let Some((start, end)) = parse_range(range_str, file_size) {
                let length = end - start + 1;

                file.seek(SeekFrom::Start(start)).await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

                let mut buffer = vec![0u8; length as usize];
                file.read_exact(&mut buffer).await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

                response_headers.insert(
                    axum::http::header::CONTENT_LENGTH,
                    HeaderValue::from(length),
                );
                response_headers.insert(
                    axum::http::header::CONTENT_RANGE,
                    HeaderValue::from_str(&format!("bytes {}-{}/{}", start, end, file_size))
                        .unwrap_or_else(|e| {
                            log::warn!("Invalid CONTENT_RANGE header value: {}", e);
                            HeaderValue::from_static("bytes */*")
                        }),
                );

                return Ok((StatusCode::PARTIAL_CONTENT, response_headers, buffer).into_response());
            }
        }
    }

    response_headers.insert(
        axum::http::header::CONTENT_LENGTH,
        HeaderValue::from(file_size),
    );

    let mut buffer = Vec::with_capacity(file_size as usize);
    file.read_to_end(&mut buffer).await.map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok((StatusCode::OK, response_headers, buffer).into_response())
}
