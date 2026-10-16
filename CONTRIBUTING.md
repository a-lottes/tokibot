# Contributing to Tokibot

Thanks for wanting to help. Tokibot is a hobby project with one maintainer, so small,
focused changes get merged fastest.

## Reporting a problem

Open an issue with the "Bug" form. Most problems depend on the hardware and the setup,
so please include:

* the Pi (Zero 2 W or Zero W) and the display (e.g. 2.13" V4)
* the image or app version (shown on the settings page and in `tokibot.toml`)
* how the computer reaches the gotchi: USB cable, Wi-Fi or a relay
* your operating system and coding agent(s)
* what the client says: `sh ~/.tokibot/tokibot.sh test`

Check the [FAQ](https://tokibot.lottes.dev/faq.html) first; many USB, driver and Wi-Fi
questions are answered there.

## Working on the code

Everything runs without hardware:

```
make test                # app tests
make test-site           # highscore API tests (needs Node)
make sim                 # the gotchi in your browser: http://localhost:8765/
make sim FAKE=Mochi      # with a pretend gotchi nearby to make friends with
```

Building an image needs a Debian or Ubuntu machine and about an hour the first time
(`make zero2w`). For app changes you don't need one: `make bundle` and `make update`
send the app to a running gotchi.

Some house rules:

* One topic per pull request, with a test where the change can be tested.
* Python 3.9 or newer; on the gotchi the standard library plus Pillow and PyNaCl
  (`python3 -m pip install pillow pynacl` for the tests). New dependencies
  make the image bigger, so please ask in an issue first.
* Keep the old names that still appear in the code (`claudegotchi` in the key
  derivation, backup format, config path and headers). They keep older gotchis,
  backups and clients working after the rename.
* User-facing changes go into `CHANGELOG.md` under the next version.
* The website lives in `docs/`. `docs/faq.html` is generated from `docs/faq.md`
  (`make faq`), the figures with `make figures`.

By contributing you agree that your work is published under the project's
[MIT licence](LICENSE).
