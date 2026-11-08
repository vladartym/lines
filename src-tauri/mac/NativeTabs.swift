// The native parts of the Mac app, in Liquid Glass, as SwiftUI views over the page: the floating tab bar of the iPhone
// (gen/apple/Sources/lines/NativeTabs.swift), and at the top the menu of the lines and the button of a new text or call.
// The page hides its own controls when this returns true. A click goes to the page with window.linesTab or
// window.linesNative. build.rs compiles this file into the app.
import AppKit
import SwiftUI
import WebKit

// {"tab": "messages", "hidden": false}. False before macOS 26 or with no web view, and the page then shows its own bar.
@_cdecl("lines_native_tabs")
public func linesNativeTabs(_ state: UnsafePointer<CChar>) -> Bool {
    guard #available(macOS 26.0, *) else { return false }
    guard let data = String(cString: state).data(using: .utf8),
          let state = try? JSONDecoder().decode(TabsState.self, from: data) else { return false }
    if Thread.isMainThread {
        return MainActor.assumeIsolated { NativeTabs.shared.show(state) }
    }
    DispatchQueue.main.async { _ = NativeTabs.shared.show(state) }
    return true
}

struct TabsState: Decodable {
    let tab: String
    let hidden: Bool
    // The line that texts and calls go out from, every line, and the button at the top right: "compose", "contact" or "".
    let line: String?
    let lines: [Line]?
    let action: String?
}

struct Line: Decodable, Identifiable {
    let did: String
    let title: String
    let unread: Int
    var id: String { did }
}

@available(macOS 26.0, *)
@MainActor @Observable
final class NativeTabs {
    static let shared = NativeTabs()

    // The id of each tab in the page, its title and its SF Symbol: the same as on the iPhone.
    static let tabs = [
        ("messages", "Messages", "message.fill"),
        ("calls", "Calls", "phone.fill"),
        ("keypad", "Keypad", "circle.grid.3x3.fill"),
        ("voicemail", "Voicemail", "recordingtape"),
    ]
    // The space between the bar and the bottom of the window: the gutter of the page (--gutter in src/app.css).
    private static let margin: CGFloat = 16

    var tab = "messages"
    var line = ""
    var lines: [Line] = []
    var action = ""
    @ObservationIgnored private var host: NSHostingView<TabBar>?
    @ObservationIgnored private var top: NSHostingView<TopBar>?
    @ObservationIgnored private weak var web: WKWebView?

    func show(_ state: TabsState) -> Bool {
        guard let web = webView(), let parent = web.superview else { return false }
        tab = state.tab
        let host = self.host ?? {
            let host = NSHostingView(rootView: TabBar(model: self))
            host.translatesAutoresizingMaskIntoConstraints = false
            // Next to the web view, not in it, so the clicks on the bar go to the bar.
            parent.addSubview(host, positioned: .above, relativeTo: web)
            NSLayoutConstraint.activate([
                host.centerXAnchor.constraint(equalTo: web.centerXAnchor),
                host.bottomAnchor.constraint(equalTo: web.bottomAnchor, constant: -Self.margin),
            ])
            self.host = host
            return host
        }()
        host.isHidden = state.hidden
        line = state.line ?? ""
        lines = state.lines ?? []
        action = state.action ?? ""
        let top = self.top ?? {
            let top = NSHostingView(rootView: TopBar(model: self))
            top.translatesAutoresizingMaskIntoConstraints = false
            parent.addSubview(top, positioned: .above, relativeTo: web)
            // The middle of the bar of the page: 28 points of title bar, then half of its 44 points.
            let margin = Self.margin
            NSLayoutConstraint.activate([
                top.leadingAnchor.constraint(equalTo: web.leadingAnchor, constant: margin),
                top.trailingAnchor.constraint(equalTo: web.trailingAnchor, constant: -margin),
                top.centerYAnchor.constraint(equalTo: web.topAnchor, constant: 50),
            ])
            self.top = top
            return top
        }()
        top.isHidden = state.hidden
        // The page leaves this room under its lists, and none while the bar hides, as in a conversation.
        let room = state.hidden ? 0 : Int(host.fittingSize.height + Self.margin * 2)
        web.evaluateJavaScript("document.documentElement.style.setProperty('--tabs', '\(room)px')")
        return true
    }

    func pick(_ id: String) {
        tab = id
        web?.evaluateJavaScript("window.linesTab?.('\(id)')")
    }

    // "line" with the number of a line, "action", "numbers" or "settings".
    func send(_ kind: String, _ value: String = "") {
        if kind == "line" { line = value }
        web?.evaluateJavaScript("window.linesNative?.('\(kind)', '\(value)')")
    }

    private func webView() -> WKWebView? {
        if let web { return web }
        web = NSApp.windows.lazy.compactMap { $0.contentView.flatMap(Self.find) }.first
        return web
    }

    private static func find(_ view: NSView) -> WKWebView? {
        if let web = view as? WKWebView { return web }
        return view.subviews.lazy.compactMap(find).first
    }
}

@available(macOS 26.0, *)
struct TabBar: View {
    let model: NativeTabs

    var body: some View {
        HStack(spacing: 0) {
            ForEach(NativeTabs.tabs, id: \.0) { item in
                let (id, title, symbol) = item
                let open = model.tab == id
                Button { model.pick(id) } label: {
                    VStack(spacing: 3) {
                        Image(systemName: symbol).font(.system(size: 18, weight: .medium))
                        Text(title).font(.system(size: 10, weight: .semibold))
                    }
                    .frame(width: 84, height: 50)
                    .foregroundStyle(open ? Color.blue : Color.primary)
                    .background {
                        if open { Capsule().fill(.primary.opacity(0.1)) }
                    }
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(4)
        .glassEffect(.regular.interactive(), in: .capsule)
        .animation(.smooth(duration: 0.25), value: model.tab)
    }
}

// The top of the page: the menu of the lines at the left, and the button of a new text or call at the right.
@available(macOS 26.0, *)
struct TopBar: View {
    let model: NativeTabs

    var body: some View {
        HStack {
            Menu {
                ForEach(model.lines) { item in
                    let title = item.unread > 0 ? "\(item.title)  (\(item.unread))" : item.title
                    Button { model.send("line", item.did) } label: {
                        if item.did == model.line { Label(title, systemImage: "checkmark") } else { Text(title) }
                    }
                }
                Divider()
                Button("Numbers…") { model.send("numbers") }
                Button("Settings…") { model.send("settings") }
            } label: {
                HStack(spacing: 5) {
                    Text(model.lines.first { $0.did == model.line }?.title ?? "…")
                        .font(.system(size: 13, weight: .semibold))
                    Image(systemName: "chevron.down").font(.system(size: 9, weight: .bold))
                }
            }
            .menuStyle(.button)
            .menuIndicator(.hidden)
            .buttonStyle(.glass)
            .fixedSize()
            Spacer()
            if !model.action.isEmpty {
                Button { model.send("action") } label: {
                    Image(systemName: model.action == "compose" ? "square.and.pencil" : "person.crop.circle.badge.plus")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(Color.blue)
                }
                .buttonStyle(.glass)
                .buttonBorderShape(.circle)
            }
        }
        .controlSize(.large)
    }
}
