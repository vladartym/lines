// Lines: the texts and the calls of the VoIP.ms numbers, through the Lines server (server/).
// The page (src/) does the work. Rust only gives it the contacts of the device and, on the iPhone, the native tab bar.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .invoke_handler(tauri::generate_handler![contacts, native_tabs]);
    #[cfg(target_os = "ios")]
    let app = app.plugin(tauri_plugin_notifications::init());
    app.run(tauri::generate_context!()).expect("Lines could not start");
}

// contacts.m, for the Mac and the iPhone.
unsafe extern "C" {
    fn lines_contacts() -> *mut std::ffi::c_char;
}

// gen/apple/Sources/lines/NativeTabs.swift in the Xcode project of the iPhone app, and mac/NativeTabs.swift on the Mac.
#[cfg(any(target_os = "ios", target_os = "macos"))]
unsafe extern "C" {
    fn lines_native_tabs(state: *const std::ffi::c_char) -> bool;
}

// The contacts with a phone number, as JSON: [{"name": "...", "number": "..."}]. The first call asks for access. It
// waits for that answer, so it runs off the main thread.
#[tauri::command]
async fn contacts() -> String {
    tauri::async_runtime::spawn_blocking(|| unsafe {
        let raw = lines_contacts();
        let json = std::ffi::CStr::from_ptr(raw).to_string_lossy().into_owned();
        libc_free(raw.cast());
        json
    })
    .await
    .unwrap_or_else(|_| "[]".into())
}

unsafe extern "C" {
    #[link_name = "free"]
    fn libc_free(p: *mut std::ffi::c_void);
}

// Shows the native tab bar in Liquid Glass over the page: {"tab": "messages", "hidden": false}. False before iOS 26 and
// macOS 26, where the page keeps its own tab bar. Tauri runs a sync command on the main thread.
#[tauri::command]
fn native_tabs(state: String) -> bool {
    #[cfg(any(target_os = "ios", target_os = "macos"))]
    {
        let Ok(state) = std::ffi::CString::new(state) else { return false };
        return unsafe { lines_native_tabs(state.as_ptr()) };
    }
    #[allow(unreachable_code)]
    {
        let _ = state;
        false
    }
}
