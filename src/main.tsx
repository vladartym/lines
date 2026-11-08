import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./app.css";

// The Mac window has no title bar of its own (titleBarStyle Overlay), so the page leaves room for the window buttons.
if (/Macintosh/.test(navigator.userAgent) && !("ontouchend" in document)) document.documentElement.classList.add("mac");

// iOS: the keyboard covers the web view and WebKit moves the page up to show the text box, so the top went off the
// screen and the whole page could scroll. The app follows the visible part of the page instead (app.css), so the text
// box sits on the keyboard, as in Messages. This is the fix of Yonder (src/main.tsx there), with its measured curve
// for the close of the keyboard.
const vv = window.visualViewport;
if (/iPhone/.test(navigator.userAgent) && vv) {
  const html = document.documentElement;
  // The height of the visible part of the page with no keyboard.
  let full = vv.height;
  const fit = () => {
    // While the keyboard closes, visualViewport still gives the size with the keyboard for a short time.
    if (html.hasAttribute("data-closing") && full - vv.height > 100) return;
    if (!html.hasAttribute("data-keyboard")) full = vv.height;
    html.style.setProperty("--vv-height", `${vv.height}px`);
    html.style.setProperty("--vv-top", `${vv.offsetTop}px`);
    // iOS 26 can also make the web view shorter, so a text field with focus counts as the keyboard too.
    const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName ?? "");
    html.toggleAttribute("data-keyboard", typing || innerHeight - vv.height > 100);
  };
  html.dataset.viewport = "";
  fit();
  vv.addEventListener("resize", fit);
  vv.addEventListener("scroll", fit);
  // WebKit slides the page back down over about 0.3 s when the keyboard closes, but visualViewport gives the end at
  // once. So the app goes to the end with a transition that follows the slide (app.css).
  let closing: ReturnType<typeof setTimeout> | undefined;
  addEventListener("focusin", () => (html.removeAttribute("data-closing"), fit()));
  addEventListener("focusout", (e: FocusEvent) => {
    if (/^(INPUT|TEXTAREA)$/.test((e.relatedTarget as Element | null)?.tagName ?? "") || !html.hasAttribute("data-keyboard")) return void setTimeout(fit);
    html.setAttribute("data-closing", "");
    html.removeAttribute("data-keyboard");
    html.style.setProperty("--vv-top", "0px");
    html.style.setProperty("--vv-height", `${full}px`);
    clearTimeout(closing);
    closing = setTimeout(() => (html.removeAttribute("data-closing"), fit()), 400);
  });
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
