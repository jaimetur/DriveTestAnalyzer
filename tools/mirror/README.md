# Mirror of the development environment

`tools/mirror` keeps a second Mac of the network as a **mirror** of this development environment: the same checkout (Git history and uncommitted changes included) and the same configuration and data, served by the application in *mirror mode*. It exists for a development Mac that no other device can reach (a managed laptop whose network closes every incoming connection): the mirror is reachable from any phone or computer of the network, and every connection goes **from the development Mac to the mirror** over SSH, so nothing has to reach the development Mac.

## What is kept in step

| What | When | How |
| --- | --- | --- |
| The checkout, `.git` included (without the Python environments `.venv*`, the caches, `node_modules` and the runtime files of the macOS launcher) | within seconds of a change (`fswatch`) | `rsync --delete` over SSH. The mirror application restarts when Python sources or `storage-paths.conf` changed, and gets its dependencies installed first when `requirements.txt` changed. |
| The configuration and data folders (`~/DriveTestAnalyzer/config` and `data`) | every 10 minutes (`--interval`), or `data` by hand | Files go straight into the folders of the mirror while its application runs. Each SQLite database that changed is copied as an online backup (`sqlite3 .backup`, consistent while the application keeps writing), sent to `.mirror-incoming/` of the mirror and put in place as an APFS clone (an instant, whatever its size) while the mirror application is stopped for a few seconds; databases deleted on the development Mac are deleted on the mirror. |

Left out: `scheduled-backups/`, `transfer-packages/`, the workspace trash, the caches (`.cache/` of the workspaces, `.map-tiles-cache/`), the upload sessions and stop requests, `config/tools/` (the AI tools installed for one Mac) and `config/ai-credentials.json` (the AI credentials of the users). The mirror makes its own caches.

The development Mac is the only place to change things: what is changed on the mirror is overwritten by the next synchronization, and the mirror says so on every page. In mirror mode (`DRIVETEST_ANALYZER_MIRROR_OF`, set by the agent of the mirror application) the application runs no recurring backups or Reporting schedules and sends no emails, which would otherwise be made twice. At startup, the mirror points the workspace registry and the paths the workspace databases store at its own storage folder (`/Users/<mirror user>/DriveTestAnalyzer`), as it does for any copied data folder.

## Requirements

- Development Mac: Homebrew `rsync` (3.x; the `rsync` of macOS is openrsync, which lacks what the synchronization uses) and `fswatch`: `brew install rsync fswatch`. `sqlite3` comes with macOS.
- Mirror Mac: **Remote Login** on (System Settings → General → Sharing), Python 3.15 and Homebrew (`install` adds `rsync` 3 with it when the mirror has none). The checkout of the mirror must not hold changes of its own, and its storage folder is set aside when it holds data (`--replace-mirror-data`, kept beside it renamed `…before-mirror-<date>`).
- Both Macs on the same network, the mirror on while it is wanted; the agents try again at the next change or interval when the mirror is off.

## Install

On the development Mac, in the checkout:

```bash
tools/mirror/mirror-sync.sh key
```

prints the public key of the mirror (`~/.ssh/drivetest-analyzer-mirror`, created the first time, without a passphrase so that the agents can use it). Add it to `~/.ssh/authorized_keys` of the user of the mirror Mac, then:

```bash
tools/mirror/mirror-sync.sh install --host user@192.168.1.17 --repo /Users/user/PycharmProjects/DriveTestAnalyzer --storage /Users/user/DriveTestAnalyzer --label "the development Mac" --replace-mirror-data
```

`install` checks the key, installs rsync 3 on the mirror when it is missing, synchronizes the checkout, creates the `.venv` of the mirror (Python 3.15) and installs its dependencies, stops a DriveTest Analyzer server already listening on the port of the mirror (the macOS launcher, which is also taken out of the login items when macOS lets a remote session do it), sets the existing storage aside, writes the launchd agent of the mirror application (`com.drivetestanalyzer.mirror-app`: port 7278 or `--port`, `DRIVETEST_ANALYZER_MIRROR_OF` with the label, no Design warm-up), runs the first data synchronization (as long as copying the data over the network takes; the mirror application starts once the databases are applied) and installs the two agents of the development Mac: `com.drivetestanalyzer.mirror-watch` (the checkout, on every change) and `com.drivetestanalyzer.mirror-data` (the data, every `--interval` seconds, 600 by default). Then open `http://<mirror>:7278` from any device of the network.

The settings stay in `~/.config/drivetest-analyzer/mirror.conf` on the development Mac and `~/.config/drivetest-analyzer/mirror-app.conf` on the mirror; the database snapshots, the manifest and the lock in `~/.local/state/drivetest-analyzer-mirror/`; the logs in `~/Library/Logs/` (`drivetest-analyzer-mirror.log` with every synchronization, and one log per agent on each Mac).

## Commands

| Command | Does |
| --- | --- |
| `tools/mirror/mirror-sync.sh status` | The last synchronizations, the agents of the development Mac and the health of the mirror application. |
| `tools/mirror/mirror-sync.sh code` | Synchronize the checkout now. |
| `tools/mirror/mirror-sync.sh data` | Synchronize the configuration and data folders now (without waiting for the interval). |
| `tools/mirror/mirror-sync.sh all` | Both. |
| `tools/mirror/mirror-sync.sh restart-mirror` | Restart the mirror application. |
| `tools/mirror/mirror-sync.sh uninstall [--mirror]` | Remove the agents of the development Mac; with `--mirror`, also the agent of the mirror application. The checkout and the data of the mirror stay. |
| `tools/mirror/mirror-remote.sh status` (on the mirror) | The agent, the application and the storage of the mirror. |

`install` can be run again with other options; it keeps the key and the storage already set up.

## Limits

- One direction. The mirror is a copy to look at the development environment from any device: anything done on it (a ticket, a template, a report) lasts until the next synchronization. To work on the mirror Mac instead, stop the agents (`uninstall`) first.
- The data reaches the mirror a few minutes after the development Mac (the interval), the checkout within seconds. A synchronization that finds the mirror off is tried again at the next change or interval.
- The first data synchronization copies every CDR and output over the network (tens of GB over Wi-Fi take a while); the next ones send only what changed.
- The mirror application restarts, for a few seconds, each time a database changed or Python sources changed; a page open on it reloads afterwards.
