// main.swift - "Champions Setup" for macOS: one window that finds the player's own disc image of Champions: Return to
// Arms (US, SLUS-20973, v2.00), makes sure Apple's command line tools are there, and runs setup-mac.sh (beside it in the
// application's Resources) with a progress bar.  It holds nothing of the game; the disc image is only read.
//
// Built by tools/install/setup/build_setups.py (swiftc, ad-hoc signature).  No storyboard, no package: AppKit only.
import AppKit
import Foundation
import UniformTypeIdentifiers

let elfName = "SLUS_209.73"
let elfCRC: UInt32 = 0x4028A55F

// ---- the disc image ---------------------------------------------------------------------------------------------
/// True when the file is an ISO 9660 image whose root holds the US v2.00 executable (PCSX2's checksum 4028A55F:
/// the XOR of its 32-bit words).  Reads the directory and the executable only.
func isRightDisc(_ path: String) -> Bool {
    guard let f = FileHandle(forReadingAtPath: path) else { return false }
    defer { try? f.close() }
    func read(_ offset: UInt64, _ count: Int) -> Data? {
        do { try f.seek(toOffset: offset); return try f.read(upToCount: count) } catch { return nil }
    }
    func u32(_ d: Data, _ at: Int) -> UInt32 {
        let b = [UInt8](d[d.startIndex + at ..< d.startIndex + at + 4])
        return UInt32(b[0]) | UInt32(b[1]) << 8 | UInt32(b[2]) << 16 | UInt32(b[3]) << 24
    }
    guard let pvd = read(16 * 2048, 2048), pvd.count == 2048,
          String(bytes: pvd[pvd.startIndex + 1 ..< pvd.startIndex + 6], encoding: .ascii) == "CD001" else { return false }
    let rootLBA = u32(pvd, 156 + 2), rootSize = u32(pvd, 156 + 10)
    guard rootSize > 0, rootSize < 1 << 20, let dir = read(UInt64(rootLBA) * 2048, Int(rootSize)) else { return false }
    let bytes = [UInt8](dir)
    var at = 0
    while at < bytes.count {
        let length = Int(bytes[at])
        if length == 0 { at = (at / 2048 + 1) * 2048; continue }
        if at + 33 > bytes.count || at + length > bytes.count { break }
        let nameLength = Int(bytes[at + 32])
        if at + 33 + nameLength <= bytes.count, bytes[at + 25] & 2 == 0,
           let name = String(bytes: bytes[at + 33 ..< at + 33 + nameLength], encoding: .isoLatin1),
           name.uppercased().split(separator: ";").first.map(String.init) == elfName {
            let record = Data(bytes[at ..< at + length])
            let lba = u32(record, 2), size = u32(record, 10)
            guard size > 1_000_000, size < 20_000_000, let elf = read(UInt64(lba) * 2048, Int(size)), elf.count == Int(size) else { return false }
            let e = [UInt8](elf)
            guard e[0] == 0x7F, e[1] == 0x45, e[2] == 0x4C, e[3] == 0x46 else { return false }
            var crc: UInt32 = 0
            var i = 0
            while i + 4 <= e.count {
                crc ^= UInt32(e[i]) | UInt32(e[i + 1]) << 8 | UInt32(e[i + 2]) << 16 | UInt32(e[i + 3]) << 24
                i += 4
            }
            return crc == elfCRC
        }
        at += length
    }
    return false
}

/// The first right disc image (.iso, 1 to 9 GB) in the usual places, two folder levels deep.  The places are looked at
/// one after the other and the search stops at the first hit, so macOS asks about one folder at most.
func findDisc() -> String? {
    let fm = FileManager.default
    let home = fm.homeDirectoryForCurrentUser.path
    var places = ["\(home)/Library/Application Support/Play-RTA", "\(home)/Downloads", "\(home)/Desktop", "\(home)/Documents"]
    if let volumes = try? fm.contentsOfDirectory(atPath: "/Volumes") {
        places += volumes.sorted().map { "/Volumes/\($0)" }
    }
    var seen = Set<String>()
    for top in places {
        var stack: [(String, Int)] = [(top, 0)]
        while let (folder, depth) = stack.popLast() {
            guard let names = try? fm.contentsOfDirectory(atPath: folder) else { continue }
            for name in names.sorted() where !name.hasPrefix(".") {
                let path = folder + "/" + name
                var isDir: ObjCBool = false
                guard fm.fileExists(atPath: path, isDirectory: &isDir) else { continue }
                if isDir.boolValue {
                    if depth < 2 && !name.hasSuffix(".app") && !name.hasSuffix(".photoslibrary") { stack.append((path, depth + 1)) }
                    continue
                }
                guard name.lowercased().hasSuffix(".iso") else { continue }
                let real = (path as NSString).resolvingSymlinksInPath
                guard !seen.contains(real),
                      let size = (try? fm.attributesOfItem(atPath: real))?[.size] as? NSNumber,
                      size.int64Value > 1_000_000_000, size.int64Value < 9_000_000_000 else { continue }
                seen.insert(real)
                if isRightDisc(path) { return path }
            }
        }
    }
    return nil
}

// ---- Apple's command line tools -----------------------------------------------------------------------------------
func run(_ tool: String, _ args: [String]) -> (Int32, String) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: tool)
    p.arguments = args
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = FileHandle.nullDevice
    do { try p.run() } catch { return (-1, "") }
    let out = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, String(data: out, encoding: .utf8) ?? "")
}

func haveCommandLineTools() -> Bool {
    let (code, dir) = run("/usr/bin/xcode-select", ["-p"])
    let path = dir.trimmingCharacters(in: .whitespacesAndNewlines)
    guard code == 0, !path.isEmpty, FileManager.default.fileExists(atPath: path) else { return false }
    return run("/usr/bin/xcrun", ["--find", "clang++"]).0 == 0
}

// ---- the window ---------------------------------------------------------------------------------------------------
final class Setup: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    let heading = NSTextField(labelWithString: "Champions Setup")
    let message = NSTextField(wrappingLabelWithString: "")
    let bar = NSProgressIndicator()
    let detail = NSTextField(labelWithString: "")
    let primary = NSButton(title: "Start", target: nil, action: nil)
    let secondary = NSButton(title: "Show details", target: nil, action: nil)
    let logView = NSTextView()
    var logScroll: NSScrollView!
    var disc: String?
    var task: Process?
    var finished = false
    var programPath = ""

    func applicationDidFinishLaunching(_ note: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 250), styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Champions Setup"
        window.delegate = self
        window.minSize = NSSize(width: 480, height: 230)
        heading.font = .systemFont(ofSize: 20, weight: .semibold)
        message.font = .systemFont(ofSize: 13)
        message.preferredMaxLayoutWidth = 512
        detail.font = .systemFont(ofSize: 11)
        detail.textColor = .secondaryLabelColor
        detail.lineBreakMode = .byTruncatingMiddle
        bar.isIndeterminate = false
        bar.minValue = 0
        bar.maxValue = 100
        bar.style = .bar
        primary.bezelStyle = .rounded
        primary.keyEquivalent = "\r"
        primary.target = self
        primary.action = #selector(primaryClicked)
        primary.isHidden = true
        secondary.bezelStyle = .rounded
        secondary.target = self
        secondary.action = #selector(toggleLog)
        logView.isEditable = false
        logView.font = .monospacedSystemFont(ofSize: 10, weight: .regular)
        logScroll = NSScrollView()
        logScroll.documentView = logView
        logScroll.hasVerticalScroller = true
        logScroll.isHidden = true
        logView.autoresizingMask = [.width]
        logView.isVerticallyResizable = true

        let buttons = NSStackView(views: [secondary, NSView(), primary])
        buttons.orientation = .horizontal
        let stack = NSStackView(views: [heading, message, bar, detail, logScroll, buttons])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 20, left: 24, bottom: 20, right: 24)
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView = stack
        for v in [message, bar, detail, logScroll!, buttons] as [NSView] {
            v.translatesAutoresizingMaskIntoConstraints = false
            v.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -48).isActive = true
        }
        logScroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 160).isActive = true
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        say("You need your own disc image of Champions: Return to Arms (US, v2.00). Setup looks for it now and does the rest: "
            + "about 15 to 40 minutes, the Mac stays usable.", progress: 0, detail: "")
        DispatchQueue.global().async { self.checkTools() }
    }

    func say(_ text: String, progress: Double? = nil, detail d: String? = nil) {
        DispatchQueue.main.async {
            self.message.stringValue = text
            if let p = progress { self.bar.doubleValue = p }
            if let d = d { self.detail.stringValue = d }
        }
    }

    func log(_ line: String) {
        DispatchQueue.main.async {
            self.logView.textStorage?.append(NSAttributedString(string: line + "\n", attributes: [.font: self.logView.font!, .foregroundColor: NSColor.textColor]))
            self.logView.scrollToEndOfDocument(nil)
        }
    }

    func button(_ title: String?) {
        DispatchQueue.main.async {
            if let t = title { self.primary.title = t; self.primary.isHidden = false } else { self.primary.isHidden = true }
        }
    }

    @objc func toggleLog() {
        logScroll.isHidden.toggle()
        secondary.title = logScroll.isHidden ? "Show details" : "Hide details"
        var frame = window.frame
        let grow: CGFloat = logScroll.isHidden ? -200 : 200
        frame.size.height += grow
        frame.origin.y -= grow
        window.setFrame(frame, display: true, animate: true)
    }

    enum Next { case none, pickDisc, retry, startGame, quit }
    var next = Next.none

    @objc func primaryClicked() {
        switch next {
        case .pickDisc: pickDisc()
        case .retry: button(nil); DispatchQueue.global().async { self.checkTools() }
        case .startGame: NSWorkspace.shared.open(URL(fileURLWithPath: programPath))
        case .quit: NSApp.terminate(nil)
        case .none: break
        }
    }

    // 1. Apple's command line tools: the compiler and python3
    func checkTools() {
        if haveCommandLineTools() { findTheDisc(); return }
        say("Apple's command line developer tools are needed (the compiler). A window from Apple asks to install them: "
            + "click Install there. Setup goes on by itself when they are installed (5 to 15 minutes).", progress: 0, detail: "Waiting for Apple's command line tools")
        _ = run("/usr/bin/xcode-select", ["--install"])
        var waited = 0
        while !haveCommandLineTools() {
            Thread.sleep(forTimeInterval: 5)
            waited += 5
            if waited % 300 == 0 { _ = run("/usr/bin/xcode-select", ["--install"]) }   // the window was closed: ask again
        }
        findTheDisc()
    }

    // 2. the disc image
    func findTheDisc() {
        say("Looking for your disc image in Downloads, Desktop, Documents and on mounted drives ...", progress: 1, detail: "")
        if let found = findDisc() {
            disc = found
            log("disc image: " + found)
            startBuild()
        } else {
            say("Setup did not find your disc image of Champions: Return to Arms (US, SLUS-20973, v2.00). Choose the .iso file.",
                progress: 1, detail: "")
            next = .pickDisc
            button("Choose disc image ...")
            DispatchQueue.main.async { self.pickDisc() }
        }
    }

    func pickDisc() {
        let panel = NSOpenPanel()
        panel.title = "Your disc image of Champions: Return to Arms (.iso)"
        panel.message = "Choose your disc image of Champions: Return to Arms (US, SLUS-20973, v2.00)"
        panel.allowedContentTypes = [UTType(filenameExtension: "iso") ?? .diskImage]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let path = url.path
        button(nil)
        DispatchQueue.global().async {
            if isRightDisc(path) {
                self.disc = path
                self.log("disc image: " + path)
                self.startBuild()
            } else {
                self.say("That file is not the US release, version 2.00, of Champions: Return to Arms (SLUS-20973). "
                         + "Choose another disc image.", progress: 1, detail: path)
                self.button("Choose disc image ...")
            }
        }
    }

    // 3. the build: setup-mac.sh, its "@progress" lines on the bar
    func startBuild() {
        guard let disc = disc, let res = Bundle.main.resourcePath else { return }
        say("Building Champions from your disc image. This takes 15 to 40 minutes; you can keep using the Mac.", progress: 1, detail: "Starting")
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [res + "/setup-mac.sh", "--disc", disc, "--resources", res, "--no-start"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        var pending = Data()
        var failure = ""
        pipe.fileHandleForReading.readabilityHandler = { h in
            let data = h.availableData
            if data.isEmpty { return }
            pending.append(data)
            while let nl = pending.firstIndex(of: 10) {
                let line = String(data: pending[pending.startIndex ..< nl], encoding: .utf8) ?? ""
                pending.removeSubrange(pending.startIndex ... nl)
                if line.hasPrefix("@progress ") {
                    let rest = line.dropFirst(10)
                    let parts = rest.split(separator: " ", maxSplits: 1)
                    if let n = Double(parts.first ?? "") {
                        self.say("Building Champions from your disc image. This takes 15 to 40 minutes; you can keep using the Mac.",
                                 progress: n, detail: parts.count > 1 ? String(parts[1]) : "")
                    }
                } else if line.hasPrefix("@error ") {
                    failure = String(line.dropFirst(7))
                    self.log(line)
                } else if line.hasPrefix("@done ") {
                    self.programPath = String(line.dropFirst(6))
                } else {
                    self.log(line)
                }
            }
        }
        p.terminationHandler = { proc in
            pipe.fileHandleForReading.readabilityHandler = nil
            if proc.terminationStatus == 0 && !self.programPath.isEmpty {
                self.finished = true
                self.say("Champions is ready. It is in your Applications folder and on your desktop: \"Champions\" (the native program) "
                         + "and \"Champions Godot\". Starting Champions now.", progress: 100, detail: "Done")
                self.next = .startGame
                self.button("Start Champions")
                DispatchQueue.main.async { NSWorkspace.shared.open(URL(fileURLWithPath: self.programPath)) }
            } else {
                self.say("Setup did not finish: " + (failure.isEmpty ? "see the details." : failure), detail: "")
                self.next = .retry
                self.button("Try again")
                DispatchQueue.main.async { if self.logScroll.isHidden { self.toggleLog() } }
            }
        }
        do { try p.run(); task = p } catch { say("Setup could not start its build script: \(error)"); next = .retry; button("Try again") }
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if let t = task, t.isRunning {
            let alert = NSAlert()
            alert.messageText = "Stop the setup?"
            alert.informativeText = "Champions is being built. If you stop now, the next start of Champions Setup goes on from where it was."
            alert.addButton(withTitle: "Keep going")
            alert.addButton(withTitle: "Stop")
            if alert.runModal() == .alertFirstButtonReturn { return false }
            _ = run("/usr/bin/pkill", ["-TERM", "-P", String(t.processIdentifier)])     // the build under the script
            t.terminate()
        }
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = Setup()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
