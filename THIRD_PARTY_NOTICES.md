# Third-party notices

API Credit Code ships two small libraries inside its page (`src/api_credit_code/static/`), unchanged:

| Library | Version | Used for | License |
|---|---|---|---|
| [marked](https://github.com/markedjs/marked) | 18.3.0 | Turning Claude's Markdown into HTML | MIT, see [licenses/marked-LICENSE.md](licenses/marked-LICENSE.md) |
| [DOMPurify](https://github.com/cure53/DOMPurify) | 3.4.17 | Cleaning that HTML before it is shown | Apache-2.0 (or MPL-2.0), see [licenses/DOMPurify-LICENSE.txt](licenses/DOMPurify-LICENSE.txt) |

The downloadable Windows and Mac apps also contain the Python runtime ([PSF License](https://docs.python.org/3/license.html)) and PyInstaller's bootloader ([GPL-2.0 with an exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt) that allows bundling it into apps like this one).

Claude Code itself is not included. It is Anthropic's own program, which you install from Anthropic.
