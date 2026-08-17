import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root

  property var shell: null
  property bool syncPending: false

  readonly property string home: Quickshell.env("HOME")
  readonly property string themeNamePath: home + "/.local/state/omarchy/current/theme.name"
  readonly property string syncScript: Qt.resolvedUrl("sync-herdr-theme.py").toString().replace("file://", "")

  function sync() {
    if (syncProcess.running) {
      syncPending = true
      return
    }

    syncProcess.command = ["python3", syncScript]
    syncProcess.running = true
  }

  Process {
    id: syncProcess
    onExited: function() {
      if (!root.syncPending) return
      root.syncPending = false
      root.sync()
    }
  }

  FileView {
    path: root.themeNamePath
    watchChanges: true
    printErrors: false
    onFileChanged: root.sync()
  }

  Component.onCompleted: sync()
}
