# Developer release candidate — isolated use only

Source derives from I046 (`8e2faa3`). Historical recovery remains untouched.
This is a developer demonstration, not an employee pilot or production release.
The 21 original evidence fixtures are real pending-review material, not synthetic
policies. They remain visibly unapproved and cannot be promoted by this app.

## Run on the workstation

From this release directory, using the existing Python installation:

```powershell
$env:FAWRY_RC_DEVELOPER_TOKEN = '<private random developer token, at least 32 characters>'
& 'D:\FawryChatbotPreparation\Scripts\python.exe' -B -X utf8 source/demo_app.py --technical-fixture-demo --workspace '<new disposable local directory>'
```

Open the printed `http://127.0.0.1:<port>` URL. Enter the developer token in the
page, connect, and create conversations. The token is never placed in the URL.
Use a new workspace for every launch; existing workspaces are not overwritten.
The service binds only loopback and has no production/employee mode. Do not
forward the port, expose it over LAN, or use actual customer information.

The in-memory developer cookie expires after one hour, uses HttpOnly and
SameSite=Strict, and is not production identity infrastructure. The demo uses
HTTP on loopback; employee authentication, TLS and operational security reviews
are still required before any separately authorized pilot.

## Stop and rollback

Ctrl+C stops the foreground server. Close the browser and remove the process's
developer token environment variable. Sessions disappear on restart. No service
is installed and no production pointer is changed. Retain test results and
audit receipts. To revert candidate changes, start a new isolated checkout of
the recorded tested commit; verify its SHA-256 source manifest before startup.
Do not restore or edit production as part of developer-demo rollback.

The historical protected backup has not been restored/tested by this workstream;
its existence or past hashes do not prove operational rollback capability.

## Reproduce local assessment

```powershell
& 'D:\FawryChatbotPreparation\Scripts\python.exe' -B -X utf8 environment_validation/inspect_environment.py
& 'D:\FawryChatbotPreparation\Scripts\python.exe' -B -X utf8 end_to_end/assess_all_demo_checks.py
& 'D:\FawryChatbotPreparation\Scripts\python.exe' -B -X utf8 end_to_end/run_historical.py
```

Every run creates a fresh result directory. Read individual failed assertions;
process exit success alone is not application acceptance. The retained Core
results do not measure native model latency, memory, throughput or offline
Windows Server readiness.
