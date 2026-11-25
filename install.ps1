# API Credit Code installer for Windows. In PowerShell:
#
#   irm https://raw.githubusercontent.com/kidze/api-credit-code/main/install.ps1 | iex
#
# What it does: finds Python 3.10 or newer (or installs Python 3.13 from python.org with winget), installs
# API Credit Code for your user with pip, adds Start menu and Desktop icons, and opens it in your browser.
# Nothing runs as administrator. To update, run the same line again.
#
# For testing: ACC_SOURCE installs from another place (a folder or a .zip), ACC_NO_LAUNCH=1 skips the icons and
# runs a self-test instead of opening the app.

function Install-ApiCreditCode {
    # Windows PowerShell 5.1 turns anything a program writes to stderr into an error, and with 'Stop' that would end
    # the install on a mere pip warning. So: 'Continue', exit codes checked by hand, and no double quotes inside the
    # arguments given to programs (5.1 drops them).
    $ErrorActionPreference = 'Continue'
    $source = if ($env:ACC_SOURCE) { $env:ACC_SOURCE } else { 'https://github.com/kidze/api-credit-code/archive/refs/heads/main.zip' }
    $check = 'import sys; print(sys.executable * (sys.version_info >= (3, 10)))'

    function Find-Python {
        $found = @()
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $found += (& py -3 -c $check 2>$null)
        }
        foreach ($name in 'python', 'python3') {
            $cmd = Get-Command $name -ErrorAction SilentlyContinue
            # skip the Microsoft Store stub, which only opens the Store
            if ($cmd -and $cmd.Source -notlike '*\WindowsApps\*') {
                $found += (& $cmd.Source -c $check 2>$null)
            }
        }
        foreach ($v in '313', '314', '312', '311', '310') {  # a fresh python.org install, before PATH catches up
            $found += "$env:LOCALAPPDATA\Programs\Python\Python$v\python.exe"
        }
        return $found | Where-Object { $_ -and (Test-Path -LiteralPath $_.Trim()) } | ForEach-Object { $_.Trim() } |
            Select-Object -First 1
    }

    Write-Host 'Installing API Credit Code...' -ForegroundColor Cyan

    $hasClaude = (Get-Command claude -ErrorAction SilentlyContinue) -or (Test-Path "$env:USERPROFILE\.local\bin\claude.exe")
    if (-not $hasClaude) {
        Write-Host "Claude Code isn't installed yet. Install it too (Anthropic's installer):" -ForegroundColor Yellow
        Write-Host '    irm https://claude.ai/install.ps1 | iex'
    }

    $python = Find-Python
    if (-not $python) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/ and run this again.'
        }
        Write-Host 'Installing Python 3.13 from python.org (winget, for your user only)...'
        winget install --id Python.Python.3.13 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
        $python = Find-Python
        if (-not $python) {
            throw 'Python was installed, but this window cannot see it yet. Open a new PowerShell window and run the same line again.'
        }
    }
    Write-Host "Using Python: $python"

    & $python -m pip install --user --upgrade --force-reinstall --no-deps --disable-pip-version-check `
        --no-warn-script-location --quiet $source 2>&1 | ForEach-Object { Write-Host "  $_" }
    if ($LASTEXITCODE) { throw 'pip could not install API Credit Code (see the messages above).' }
    $version = & $python -m api_credit_code --version 2>&1
    if ($LASTEXITCODE) { throw "API Credit Code was installed but does not start: $version" }

    if ($env:ACC_NO_LAUNCH) {
        & $python -m api_credit_code --selftest 2>&1 | ForEach-Object { Write-Host "  $_" }
        if ($LASTEXITCODE) { throw 'The self-test failed (see the messages above).' }
    } else {
        & $python -m api_credit_code --make-launcher | Out-Null
        if ($LASTEXITCODE) {
            Write-Host "No Start menu icon was made (see above). You can start it with: & '$python' -m api_credit_code --app" -ForegroundColor Yellow
        }
        $running = $false
        try { $running = (Invoke-RestMethod -Uri 'http://127.0.0.1:8790/api/hello' -TimeoutSec 2).app -eq 'api-credit-code' } catch { }
        if ($running) {
            Write-Host 'An older copy is still running: click Quit at the bottom of its chat list, then open it again.' -ForegroundColor Yellow
        } else {
            $pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
            if (-not (Test-Path -LiteralPath $pythonw)) { $pythonw = $python }
            Start-Process -FilePath $pythonw -ArgumentList '-m', 'api_credit_code', '--app'
        }
    }

    Write-Host ''
    Write-Host "$version is installed." -ForegroundColor Green
    if (-not $env:ACC_NO_LAUNCH) {
        Write-Host 'It opens in your browser. Next time, start it from the Start menu or the Desktop icon.'
    }
}

Install-ApiCreditCode
