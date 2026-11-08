// The tab bar of iOS over the page, on iOS 26: the floating bar in Liquid Glass, as in Yonder (GlassTabBar.swift).
// The page keeps its own tab bar on the Mac and before iOS 26. A tap opens the tab in the page with window.linesTab.
import UIKit
import WebKit

// {"tab": "messages", "hidden": false}. False before iOS 26 or with no web view, and the page then shows its own bar.
// Tauri runs a sync command on the main thread.
@_cdecl("lines_native_tabs")
public func linesNativeTabs(_ state: UnsafePointer<CChar>) -> Bool {
    guard #available(iOS 26.0, *) else { return false }
    guard let data = String(cString: state).data(using: .utf8),
          let state = try? JSONDecoder().decode(NativeTabs.State.self, from: data) else { return false }
    if Thread.isMainThread {
        return MainActor.assumeIsolated { NativeTabs.shared.show(state) }
    }
    Task { @MainActor in _ = NativeTabs.shared.show(state) }
    return true
}

@available(iOS 26.0, *)
@MainActor
final class NativeTabs: NSObject, UITabBarDelegate {
    static let shared = NativeTabs()

    struct State: Decodable {
        let tab: String
        let hidden: Bool
    }

    // The id of each tab in the page, its title and its SF Symbol.
    private static let tabs = [
        ("messages", "Messages", "message.fill"),
        ("calls", "Calls", "phone.fill"),
        ("keypad", "Keypad", "circle.grid.3x3.fill"),
        ("voicemail", "Voicemail", "recordingtape"),
    ]
    private let bar = UITabBar()
    private weak var web: WKWebView?

    func show(_ state: State) -> Bool {
        guard let web = webView() else { return false }
        if bar.superview == nil {
            bar.items = Self.tabs.map { UITabBarItem(title: $0.1, image: UIImage(systemName: $0.2), tag: 0) }
            bar.delegate = self
            bar.tintColor = .systemBlue
            bar.autoresizingMask = [.flexibleWidth, .flexibleTopMargin]
            web.addSubview(bar)
            Self.prepare(web)
        }
        // The bar takes the width of the screen and goes to its bottom edge: iOS puts the glass over the home bar.
        let height = bar.sizeThatFits(web.bounds.size).height
        bar.frame = CGRect(x: 0, y: web.bounds.height - height, width: web.bounds.width, height: height)
        let open = Self.tabs.firstIndex { $0.0 == state.tab }
        bar.selectedItem = open.flatMap { bar.items?[$0] }
        bar.isHidden = state.hidden
        // The page leaves this room under its lists, and none while the bar hides, as in a conversation.
        let room = state.hidden ? 0 : Int(height)
        web.evaluateJavaScript("document.documentElement.style.setProperty('--tabs', '\(room)px')")
        return true
    }

    func tabBar(_ bar: UITabBar, didSelect item: UITabBarItem) {
        guard let index = bar.items?.firstIndex(of: item) else { return }
        web?.evaluateJavaScript("window.linesTab?.('\(Self.tabs[index].0)')")
    }

    // The keyboard of a text box, as in Messages: WebKit puts a bar with arrows and a check over it, and the window
    // behind the web view showed black at its round top corners. The bar goes, and the window, the web view and its
    // scroll view get the color of the page, light or dark with the system. The fix of Yonder (Island.swift there).
    private static func prepare(_ web: WKWebView) {
        let color = UIColor.systemBackground
        web.window?.backgroundColor = color
        web.isOpaque = false
        web.backgroundColor = color
        web.scrollView.backgroundColor = color
        web.underPageBackgroundColor = color
        guard let content = web.scrollView.subviews.first(where: { NSStringFromClass(type(of: $0)).hasPrefix("WKContent") }) else { return }
        let base: AnyClass = type(of: content)
        let name = "\(NSStringFromClass(base))_LinesNoBar"
        if NSStringFromClass(base) == name { return }
        var bare: AnyClass? = NSClassFromString(name)
        if bare == nil, let sub = objc_allocateClassPair(base, name, 0) {
            let none: @convention(block) (AnyObject) -> AnyObject? = { _ in nil }
            class_addMethod(sub, #selector(getter: UIResponder.inputAccessoryView), imp_implementationWithBlock(none), "@@:")
            objc_registerClassPair(sub)
            bare = sub
        }
        if let bare { object_setClass(content, bare) }
    }

    private func webView() -> WKWebView? {
        if let web { return web }
        let windows = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.flatMap(\.windows)
        web = windows.lazy.compactMap(Self.find).first
        return web
    }

    private static func find(_ view: UIView) -> WKWebView? {
        if let web = view as? WKWebView { return web }
        return view.subviews.lazy.compactMap(find).first
    }
}
