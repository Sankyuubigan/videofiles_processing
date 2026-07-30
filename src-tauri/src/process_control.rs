#[cfg(target_os = "windows")]
mod windows_impl {
    use std::io;
    use log::{info, warn};
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Thread32First, Thread32Next,
        TH32CS_SNAPTHREAD, THREADENTRY32,
    };
    use windows_sys::Win32::System::Threading::{OpenThread, ResumeThread, SuspendThread};
    use windows_sys::Win32::System::Threading::THREAD_SUSPEND_RESUME;

    struct ThreadHandle(HANDLE);

    impl ThreadHandle {
        fn open(tid: u32) -> Result<Self, io::Error> {
            let h = unsafe { OpenThread(THREAD_SUSPEND_RESUME, 0, tid) };
            if h.is_null() {
                return Err(io::Error::last_os_error());
            }
            Ok(ThreadHandle(h))
        }
    }

    impl Drop for ThreadHandle {
        fn drop(&mut self) {
            unsafe { CloseHandle(self.0); }
        }
    }

    fn for_each_process_thread<F>(pid: u32, mut action: F) -> Result<usize, io::Error>
    where
        F: FnMut(u32) -> Result<(), io::Error>,
    {
        let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) };
        if snapshot.is_null() {
            return Err(io::Error::last_os_error());
        }

        let mut count = 0usize;
        let mut entry: THREADENTRY32 = unsafe { std::mem::zeroed() };
        entry.dwSize = std::mem::size_of::<THREADENTRY32>() as u32;

        if unsafe { Thread32First(snapshot, &mut entry) } == 0 {
            unsafe { CloseHandle(snapshot); }
            return Err(io::Error::last_os_error());
        }

        loop {
            if entry.th32OwnerProcessID == pid {
                if let Err(e) = action(entry.th32ThreadID) {
                    warn!("Failed to operate on thread {}: {}", entry.th32ThreadID, e);
                } else {
                    count += 1;
                }
            }

            let mut next: THREADENTRY32 = unsafe { std::mem::zeroed() };
            next.dwSize = std::mem::size_of::<THREADENTRY32>() as u32;
            if unsafe { Thread32Next(snapshot, &mut next) } == 0 {
                break;
            }
            entry = next;
        }

        unsafe { CloseHandle(snapshot); }
        Ok(count)
    }

    pub fn suspend_process(pid: u32) -> Result<usize, String> {
        if pid == 0 {
            return Err("PID is 0, no process to suspend".to_string());
        }
        let count = for_each_process_thread(pid, |tid| {
            let h = ThreadHandle::open(tid)?;
            let prev = unsafe { SuspendThread(h.0) };
            if prev == u32::MAX {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        })
        .map_err(|e| format!("Failed to enumerate threads for PID {}: {}", pid, e))?;
        info!("Suspended {} threads for PID {}", count, pid);
        if count == 0 {
            return Err(format!("No threads found for PID {}", pid));
        }
        Ok(count)
    }

    pub fn resume_process(pid: u32) -> Result<usize, String> {
        if pid == 0 {
            return Err("PID is 0, no process to resume".to_string());
        }
        let count = for_each_process_thread(pid, |tid| {
            let h = ThreadHandle::open(tid)?;
            let prev = unsafe { ResumeThread(h.0) };
            if prev == u32::MAX {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        })
        .map_err(|e| format!("Failed to enumerate threads for PID {}: {}", pid, e))?;
        info!("Resumed {} threads for PID {}", count, pid);
        if count == 0 {
            return Err(format!("No threads found for PID {}", pid));
        }
        Ok(count)
    }
}

#[cfg(not(target_os = "windows"))]
mod windows_impl {
    pub fn suspend_process(_pid: u32) -> Result<usize, String> {
        Err("Pause is only supported on Windows".to_string())
    }

    pub fn resume_process(_pid: u32) -> Result<usize, String> {
        Err("Resume is only supported on Windows".to_string())
    }
}

pub use windows_impl::{suspend_process, resume_process};
