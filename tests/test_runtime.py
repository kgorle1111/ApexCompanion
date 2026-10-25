"""Runtime hardening: what keeps a broken, hung, duplicated or disk-starved coach from pretending to coach."""

import apex

# ---- the session log never kills a session


class FullDisk:
    def write(self, s):
        raise OSError(28, "No space left on device")

    def flush(self):
        raise OSError(28, "No space left on device")

    def close(self):
        raise OSError(28, "No space left on device")


def test_full_disk_warns_once_and_keeps_the_session(tmp_path, capsys):
    log = apex.EventLog(tmp_path / "s.jsonl", "abc")
    log.f.close()
    log.f = FullDisk()
    log.emit("check", n=1)
    log.emit("check", n=2)
    log.close()
    err = capsys.readouterr().err
    assert err.count("session log write failed") == 1 and "No space left" in err
