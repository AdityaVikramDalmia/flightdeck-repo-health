import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

CLI = Path(__file__).resolve().parents[1] / "bin/repo-health"


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="repo health ")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "project with spaces"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME="Example Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                        GIT_COMMITTER_NAME="Example Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
        self.git("init", "-b", "main", str(self.repo), cwd=self.base)
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", os.devnull)
        (self.repo / "tracked.txt").write_text("initial\n")
        (self.repo / ".gitignore").write_text("ignored/\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")

    def git(self, *args, cwd=None, allowed=(0,)):
        result = subprocess.run(["git", "-C", str(cwd or self.repo), *args], env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertIn(result.returncode, allowed, result.stderr.decode(errors="replace"))
        return result.stdout.decode().removesuffix("\n")

    def scan(self, *paths, expected=0, env=None, options=()):
        result = subprocess.run([str(CLI), "--json", *options, *map(str, paths or [self.repo])],
                                env=env or self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return json.loads(result.stdout)

    def configure_upstream(self, commit=None):
        commit = commit or self.git("rev-parse", "HEAD")
        self.git("config", "remote.origin.url", "ssh://example.invalid/never-accessed.git")
        self.git("config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        self.git("update-ref", "refs/remotes/origin/main", commit)
        self.git("config", "branch.main.remote", "origin")
        self.git("config", "branch.main.merge", "refs/heads/main")
        return commit

    def commit(self, message="next"):
        with (self.repo / "tracked.txt").open("a") as stream:
            stream.write(message + "\n")
        self.git("add", ".")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def test_clean_branch_without_upstream_is_unknown_sync(self):
        row = self.scan()[0]
        self.assertEqual(row["state"], "branch")
        self.assertEqual(row["branch"], "main")
        self.assertEqual(row["cleanliness"], "clean")
        self.assertEqual(row["counts"], dict(tracked=0, staged=0, unstaged=0, untracked=0, unmerged=0))
        self.assertEqual(row["sync"], "unknown")
        self.assertIsNone(row["ahead"])
        self.assertIsNone(row["behind"])

    def test_staged_unstaged_and_untracked_counts(self):
        (self.repo / "tracked.txt").write_text("staged\n")
        self.git("add", "tracked.txt")
        (self.repo / "tracked.txt").write_text("unstaged too\n")
        folder = self.repo / "new directory"
        folder.mkdir()
        (folder / "line\nbreak.txt").write_text("one")
        (folder / "-dash.txt").write_text("two")
        row = self.scan()[0]
        self.assertEqual(row["cleanliness"], "dirty")
        self.assertEqual(row["counts"], dict(tracked=1, staged=1, unstaged=1, untracked=2, unmerged=0))

    def test_rename_count_is_one_entry(self):
        self.git("mv", "tracked.txt", "renamed\nfile.txt")
        row = self.scan()[0]
        self.assertEqual(row["counts"]["tracked"], 1)
        self.assertEqual(row["counts"]["staged"], 1)
        self.assertEqual(row["counts"]["untracked"], 0)

    def test_ignored_outputs_do_not_count_as_untracked(self):
        (self.repo / "ignored").mkdir()
        (self.repo / "ignored/cache").write_text("ignored")
        row = self.scan()[0]
        self.assertEqual(row["cleanliness"], "clean")
        self.assertEqual(row["counts"]["untracked"], 0)

    def test_detached_head(self):
        self.git("checkout", "--detach")
        row = self.scan()[0]
        self.assertEqual(row["state"], "detached")
        self.assertIsNone(row["branch"])
        self.assertIsNotNone(row["head"])
        self.assertEqual(row["sync"], "unknown")

    def test_unborn_branch_and_staged_file(self):
        empty = self.base / "unborn"
        self.git("init", "-b", "first", str(empty), cwd=self.base)
        row = self.scan(empty)[0]
        self.assertEqual(row["state"], "unborn")
        self.assertEqual(row["branch"], "first")
        self.assertIsNone(row["head"])
        self.assertEqual(row["cleanliness"], "clean")
        (empty / "new.txt").write_text("new")
        self.git("add", ".", cwd=empty)
        row = self.scan(empty)[0]
        self.assertEqual(row["counts"]["staged"], 1)
        self.assertEqual(row["state"], "unborn")

    def test_equal_and_ahead_local_upstream(self):
        self.configure_upstream()
        row = self.scan()[0]
        self.assertEqual((row["sync"], row["ahead"], row["behind"]), ("equal", 0, 0))
        self.commit()
        row = self.scan()[0]
        self.assertEqual((row["sync"], row["ahead"], row["behind"]), ("ahead", 1, 0))

    def test_behind_local_upstream(self):
        original = self.git("rev-parse", "HEAD")
        newest = self.commit()
        self.configure_upstream(newest)
        self.git("reset", "--hard", original)
        row = self.scan()[0]
        self.assertEqual((row["sync"], row["ahead"], row["behind"]), ("behind", 0, 1))

    def test_diverged_local_upstream(self):
        original = self.git("rev-parse", "HEAD")
        remote = self.commit("remote side")
        self.configure_upstream(remote)
        self.git("reset", "--hard", original)
        self.commit("local side")
        row = self.scan()[0]
        self.assertEqual((row["sync"], row["ahead"], row["behind"]), ("diverged", 1, 1))

    def test_missing_remote_and_missing_tracking_ref_are_unknown(self):
        self.configure_upstream()
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        row = self.scan()[0]
        self.assertEqual(row["sync"], "unknown")
        self.assertIsNone(row["ahead"])
        self.assertIn("unavailable", row["sync_reason"])
        self.git("config", "--remove-section", "remote.origin")
        row = self.scan()[0]
        self.assertEqual(row["sync"], "unknown")
        self.assertIsNone(row["behind"])

    def test_local_branch_upstream(self):
        self.git("branch", "retained")
        self.git("branch", "--set-upstream-to=retained", "main")
        self.commit()
        row = self.scan()[0]
        self.assertEqual(row["upstream_remote"], ".")
        self.assertEqual(row["sync"], "ahead")

    def test_worktree_and_subdirectory_inputs(self):
        linked = self.base / "linked worktree"
        self.git("worktree", "add", "-b", "feature", str(linked))
        sub = linked / "subdir"
        sub.mkdir()
        rows = self.scan(self.repo, linked, sub)
        self.assertEqual([row["branch"] for row in rows], ["main", "feature", "feature"])
        self.assertEqual(rows[1]["path"], rows[2]["path"])
        self.assertTrue(all(row["cleanliness"] == "clean" for row in rows))

    def test_root_with_newline_and_symlink(self):
        moved = self.base / "renamed root\n"
        self.repo.rename(moved)
        self.repo = moved
        alias = self.base / "alias"
        alias.symlink_to(moved, target_is_directory=True)
        row = self.scan(alias)[0]
        self.assertEqual(row["path"], str(moved.resolve()))
        result = subprocess.run([str(CLI), str(alias)], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("root\\n", result.stdout)
        self.assertNotIn("root\n |", result.stdout)

    def test_missing_nonrepo_and_bare_fail_independently(self):
        bare = self.base / "bare"
        self.git("init", "--bare", str(bare), cwd=self.base)
        rows = self.scan(self.repo, self.base / "missing", self.base, bare, expected=1)
        self.assertEqual(rows[0]["cleanliness"], "clean")
        for row in rows[1:]:
            self.assertEqual(row["cleanliness"], "unknown")
            self.assertIsNone(row["counts"])
            self.assertTrue(row["errors"])

    def test_corrupt_index_is_unknown_not_clean(self):
        (self.repo / ".git/index").write_bytes(b"not an index")
        row = self.scan(expected=1)[0]
        self.assertEqual(row["cleanliness"], "unknown")
        self.assertIsNone(row["counts"])
        self.assertTrue(row["errors"])

    @unittest.skipIf(os.geteuid() == 0, "root bypasses ordinary permission checks")
    def test_unreadable_index_is_unknown_not_clean(self):
        index = self.repo / ".git/index"
        index.chmod(0)
        self.addCleanup(index.chmod, 0o600)
        row = self.scan(expected=1)[0]
        self.assertEqual(row["cleanliness"], "unknown")
        self.assertIsNone(row["counts"])

    def test_read_only_index_and_refs(self):
        index = self.repo / ".git/index"
        before = (index.read_bytes(), index.stat().st_mtime_ns, self.git("show-ref"))
        (self.repo / "tracked.txt").touch()
        self.scan()
        self.assertEqual((index.read_bytes(), index.stat().st_mtime_ns, self.git("show-ref")), before)
        self.assertFalse((self.repo / ".git/index.lock").exists())
        self.assertFalse((self.repo / ".git/FETCH_HEAD").exists())

    def test_no_network_or_fsmonitor_execution(self):
        marker = self.base / "external-command-ran"
        script = self.base / "unexpected external helper"
        script.write_text("#!/bin/sh\ntouch " + shlex.quote(str(marker)) + "\nexit 99\n")
        script.chmod(0o755)
        self.configure_upstream()
        self.git("config", "core.fsmonitor", str(script))
        self.git("config", "core.sshCommand", shlex.quote(str(script)))
        row = self.scan()[0]
        self.assertEqual(row["sync"], "equal")
        self.assertFalse(marker.exists())
        self.assertFalse((self.repo / ".git/FETCH_HEAD").exists())

    def test_git_environment_cannot_redirect_repository(self):
        other = self.base / "other"
        self.git("init", "-b", "other", str(other), cwd=self.base)
        env = dict(self.env, GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other))
        row = self.scan(env=env)[0]
        self.assertEqual(row["branch"], "main")
        self.assertEqual(row["path"], str(self.repo.resolve()))

    def test_hidden_index_flags_make_cleanliness_unknown(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.git("update-index", flag, "tracked.txt")
                (self.repo / "tracked.txt").write_text("hidden edit")
                row = self.scan()[0]
                self.assertEqual(row["cleanliness"], "unknown")
                self.assertTrue(row["warnings"])
                self.git("update-index", "--no-assume-unchanged", "--no-skip-worktree", "tracked.txt")

    def test_corrupt_head_is_not_unborn(self):
        (self.repo / ".git/refs/heads/main").write_text("f" * 40 + "\n")
        row = self.scan(expected=1)[0]
        self.assertEqual(row["state"], "unknown")
        self.assertTrue(row["errors"])

    def test_install_is_single_file_and_handles_spaces(self):
        prefix = self.base / "installed location"
        result = subprocess.run(["make", "install", "PREFIX=" + str(prefix)], cwd=CLI.parents[1],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(prefix / "bin/repo-health"), "--json", str(self.repo)],
                                cwd=self.base, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["branch"], "main")

    def test_invalid_timeout_and_missing_input(self):
        for args in ([], ["--timeout", "0", str(self.repo)], ["--timeout", "nan", str(self.repo)]):
            result = subprocess.run([str(CLI), *args], env=self.env, capture_output=True)
            self.assertEqual(result.returncode, 2)

    def wrapper(self, command, body):
        directory = self.base / "wrapper"
        directory.mkdir()
        actual = shutil.which("git")
        script = directory / "git"
        script.write_text("#!" + sys.executable + "\nimport os,sys,time\n" +
                          "if " + repr(command) + " in sys.argv[1:]:\n" +
                          "\n".join("    " + line for line in body.splitlines()) + "\n" +
                          "os.execv(" + repr(actual) + ", [" + repr(actual) + "] + sys.argv[1:])\n")
        script.chmod(0o755)
        return dict(self.env, PATH=str(directory) + os.pathsep + self.env["PATH"])

    def test_failed_ahead_query_is_unknown_not_equal(self):
        self.configure_upstream()
        env = self.wrapper("rev-list", "sys.stderr.write('synthetic object read failure'); sys.exit(128)")
        row = self.scan(env=env, expected=1)[0]
        self.assertEqual(row["sync"], "unknown")
        self.assertIsNone(row["ahead"])
        self.assertIsNone(row["behind"])
        self.assertTrue(row["errors"])

    def test_status_warning_cannot_be_reported_clean(self):
        env = self.wrapper("status", "sys.stderr.write('warning: unreadable directory'); sys.exit(0)")
        row = self.scan(env=env, expected=1)[0]
        self.assertEqual(row["cleanliness"], "unknown")
        self.assertIsNone(row["counts"])

    def test_truncated_status_is_unknown(self):
        env = self.wrapper("status", "sys.stdout.write('?? truncated'); sys.exit(0)")
        row = self.scan(env=env, expected=1)[0]
        self.assertEqual(row["cleanliness"], "unknown")
        self.assertIsNone(row["counts"])

    def test_query_timeout_is_unknown_and_bounded(self):
        env = self.wrapper("status", "time.sleep(3); sys.exit(0)")
        row = self.scan(env=env, expected=1, options=("--timeout", "0.5"))[0]
        self.assertEqual(row["cleanliness"], "unknown")
        self.assertTrue(any("timeout" in error for error in row["errors"]))

    def test_query_timeout_stops_its_helper_process(self):
        marker = self.base / "helper-must-not-finish"
        child_code = "import pathlib,sys,time;time.sleep(.5);pathlib.Path(sys.argv[1]).touch()"
        body = ("import subprocess\n"
                "subprocess.Popen([sys.executable, '-c', " + repr(child_code) + ", " + repr(str(marker)) + "], "
                "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                "time.sleep(3);sys.exit(0)")
        env = self.wrapper("status", body)
        subprocess.run(["git", "--version"], env=env, stdout=subprocess.PIPE, check=True)
        rows = self.scan(env=env, expected=1, options=("--timeout", "0.2"))
        self.assertTrue(any("git status exceeded" in item for item in rows[0]["errors"]))
        time.sleep(0.6)
        self.assertFalse(marker.exists(), "timed-out Git helper continued running")

    def test_git_transports_are_disabled_in_probe_environment(self):
        env = self.wrapper("status", "assert os.environ['GIT_ALLOW_PROTOCOL'] == ''\nassert os.environ['GIT_NO_LAZY_FETCH'] == '1'")
        row = self.scan(env=env)[0]
        self.assertEqual(row["cleanliness"], "clean")

    def test_termination_stops_owned_query_helpers(self):
        marker = self.base / "interrupted-helper-output"
        ready = self.base / "interrupted-query-ready"
        child_code = "import pathlib,sys,time;time.sleep(.5);pathlib.Path(sys.argv[1]).touch()"
        body = ("import subprocess,pathlib\n"
                "subprocess.Popen([sys.executable, '-c', " + repr(child_code) + ", " + repr(str(marker)) + "], "
                "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                "pathlib.Path(" + repr(str(ready)) + ").touch()\ntime.sleep(3);sys.exit(0)")
        env = self.wrapper("status", body)
        process = subprocess.Popen([str(CLI), "--json", str(self.repo)], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                self.assertIsNone(process.poll())
                time.sleep(.01)
            self.assertTrue(ready.exists())
            process.terminate()
            process.communicate(timeout=5)
            self.assertEqual(process.returncode, 143)
            time.sleep(.6)
            self.assertFalse(marker.exists(), "interrupted query left its helper running")
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)

    def test_symlink_loop_is_an_individual_error(self):
        loop = self.base / "loop"
        loop.symlink_to(loop)
        rows = self.scan(loop, self.repo, expected=1)
        self.assertTrue(rows[0]["errors"])
        self.assertEqual(rows[1]["cleanliness"], "clean")

    def test_split_index_inspection_does_not_refresh_shared_files(self):
        self.configure_upstream()
        self.git("update-index", "--split-index")
        shared = list((self.repo / ".git").glob("sharedindex.*"))
        self.assertTrue(shared)
        for path in shared:
            os.utime(path, (1000000000, 1000000000))
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in shared}
        row = self.scan()[0]
        after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in shared}
        self.assertEqual(before, after)
        self.assertEqual(row["cleanliness"], "unknown")
        self.assertIsNone(row["counts"])
        self.assertTrue(any("split index" in warning for warning in row["warnings"]))
        self.assertEqual(row["sync"], "equal")

    def test_multiple_merge_targets_match_the_actual_compared_upstream(self):
        original = self.configure_upstream()
        newer = self.commit("newer")
        self.git("update-ref", "refs/remotes/origin/other", newer)
        self.git("config", "--add", "branch.main.merge", "refs/heads/other")
        row = self.scan()[0]
        self.assertEqual(row["upstream"], "refs/remotes/origin/main")
        self.assertEqual(row["upstream_merge"], "refs/heads/main")
        self.assertEqual((row["sync"], row["ahead"], row["behind"]), ("ahead", 1, 0))
        self.assertTrue(any("multiple merge" in warning for warning in row["warnings"]))

    def test_table_exposes_merge_conflict_count(self):
        self.git("checkout", "-b", "other")
        (self.repo / "tracked.txt").write_text("other side\n")
        self.git("commit", "-qam", "other side")
        self.git("checkout", "main")
        (self.repo / "tracked.txt").write_text("main side\n")
        self.git("commit", "-qam", "main side")
        self.git("merge", "other", allowed=(1,))
        row = self.scan()[0]
        self.assertEqual(row["counts"]["unmerged"], 1)
        result = subprocess.run([str(CLI), str(self.repo)], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        headers = lines[0].split(" | ")
        values = lines[1].split(" | ")
        self.assertIn("UNMERGED", headers)
        self.assertEqual(values[headers.index("UNMERGED")], "1")

    def test_split_index_artifacts_block_even_when_configuration_is_false(self):
        self.git("update-index", "--split-index")
        self.git("config", "core.splitIndex", "false")
        shared = list((self.repo / ".git").glob("sharedindex.*"))
        for path in shared:
            os.utime(path, (1000000000, 1000000000))
        before = [path.stat().st_mtime_ns for path in shared]
        row = self.scan()[0]
        self.assertEqual(row["cleanliness"], "unknown")
        self.assertEqual(before, [path.stat().st_mtime_ns for path in shared])
        # A formerly split index can retain shared artifacts; that refusal is deliberate.
        self.git("update-index", "--no-split-index")
        self.assertTrue(shared)
        self.assertEqual(self.scan()[0]["cleanliness"], "unknown")

    def test_split_index_configuration_without_artifacts_is_conservative(self):
        self.git("config", "core.splitIndex", "true")
        index = self.repo / ".git/index"
        before = (index.read_bytes(), index.stat().st_mtime_ns)
        row = self.scan()[0]
        self.assertEqual(row["cleanliness"], "unknown")
        self.assertTrue(any("configured" in warning for warning in row["warnings"]))
        self.assertEqual((index.read_bytes(), index.stat().st_mtime_ns), before)
        self.assertFalse(list((self.repo / ".git").glob("sharedindex.*")))

    def test_linked_worktree_split_index_is_checked_in_its_admin_directory(self):
        linked = self.base / "linked split worktree"
        self.git("worktree", "add", "-b", "linked", str(linked))
        self.git("update-index", "--split-index", cwd=linked)
        index = Path(self.git("rev-parse", "--git-path", "index", cwd=linked))
        shared = list(index.parent.glob("sharedindex.*"))
        self.assertTrue(shared)
        for path in shared:
            os.utime(path, (1000000000, 1000000000))
        before = [path.stat().st_mtime_ns for path in shared]
        rows = self.scan(self.repo, linked)
        self.assertEqual([row["cleanliness"] for row in rows], ["clean", "unknown"])
        self.assertEqual(before, [path.stat().st_mtime_ns for path in shared])

    def test_nested_submodule_split_index_is_not_touched_by_parent_status(self):
        origin = self.base / "module source"
        self.git("clone", "--no-hardlinks", str(self.repo), str(origin), cwd=self.base)
        self.git("-c", "protocol.file.allow=always", "submodule", "add", str(origin), "outer")
        outer = self.repo / "outer"
        self.git("-c", "protocol.file.allow=always", "submodule", "add", str(origin), "inner", cwd=outer)
        self.git("commit", "-qam", "nested fixture", cwd=outer)
        self.git("commit", "-qam", "module fixture")
        inner = outer / "inner"
        self.git("update-index", "--split-index", cwd=inner)
        self.git("config", "core.splitIndex", "false", cwd=inner)
        index = Path(self.git("rev-parse", "--git-path", "index", cwd=inner))
        shared = list(index.parent.glob("sharedindex.*"))
        self.assertTrue(shared)
        for path in shared:
            os.utime(path, (1000000000, 1000000000))
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in shared}
        row = self.scan()[0]
        self.assertEqual(row["cleanliness"], "unknown")
        self.assertTrue(any("inner" in warning for warning in row["warnings"]))
        self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in shared})

    def test_allowed_absence_status_cannot_hide_query_diagnostics(self):
        env = self.wrapper("symbolic-ref", "sys.stderr.write('unable to inspect HEAD');sys.exit(1)")
        row = self.scan(env=env, expected=1)[0]
        self.assertEqual(row["state"], "unknown")
        self.assertTrue(any("unable to inspect HEAD" in error for error in row["errors"]))

    def test_unsupported_git_version_is_refused_before_status(self):
        env = self.wrapper("--version", "sys.stdout.write('git version 2.35.1\\n');sys.exit(0)")
        row = self.scan(env=env, expected=1)[0]
        self.assertEqual(row["state"], "unknown")
        self.assertIsNone(row["counts"])
        self.assertTrue(any("Git 2.36" in error for error in row["errors"]))

    def test_shallow_history_limit_is_visible_in_the_result(self):
        self.configure_upstream()
        tip = self.commit("shallow tip")
        (self.repo / ".git/shallow").write_text(tip + "\n")
        row = self.scan()[0]
        self.assertEqual((row["sync"], row["ahead"], row["behind"]), ("diverged", 1, 1))
        self.assertTrue(any("shallow history" in warning for warning in row["warnings"]))

    def test_signal_during_process_handoff_cleans_the_created_query(self):
        ready = self.base / "handoff-query-ready"
        release = self.base / "release-handoff-helper"
        marker = self.base / "handoff-helper-survived"
        child_code = (
            "import pathlib,sys,time;release=pathlib.Path(sys.argv[1]);"
            "\nwhile not release.exists(): time.sleep(.005)"
            "\npathlib.Path(sys.argv[2]).touch()"
        )
        body = ("import pathlib,subprocess\n"
                "subprocess.Popen([sys.executable,'-c'," + repr(child_code) + ","
                + repr(str(release)) + "," + repr(str(marker)) + "],"
                "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                "pathlib.Path(" + repr(str(ready)) + ").write_text(str(os.getpid()))\n"
                "time.sleep(10);sys.exit(0)")
        env = self.wrapper("status", body)
        # Delay the Popen return until the real query owns a helper, then deliver
        # TERM before Git.run has received the process object. This makes the
        # otherwise tiny spawn/assignment signal window deterministic.
        runner = (
            "import os,pathlib,runpy,signal,sys,time;"
            "namespace=runpy.run_path(sys.argv[1]);real=namespace['subprocess'].Popen;"
            "ready=pathlib.Path(sys.argv[3]);"
            "\ndef spawn(*args,**kwargs):"
            "\n process=real(*args,**kwargs)"
            "\n if 'status' in args[0]:"
            "\n  deadline=time.monotonic()+5"
            "\n  while not ready.exists() and time.monotonic()<deadline: time.sleep(.005)"
            "\n  assert ready.exists()"
            "\n  os.kill(os.getpid(),signal.SIGTERM)"
            "\n return process"
            "\nnamespace['subprocess'].Popen=spawn;"
            "signal.signal(signal.SIGTERM,lambda number,frame:sys.exit(128+number));"
            "sys.argv=[sys.argv[1],'--json',sys.argv[2]];sys.exit(namespace['main']())"
        )
        try:
            result = subprocess.run([sys.executable, "-c", runner, str(CLI), str(self.repo), str(ready)],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 143, result.stdout + result.stderr)
            release.touch()
            deadline = time.monotonic() + .5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertFalse(marker.exists(), "created query/helper survived an interrupted ownership handoff")
        finally:
            release.touch()
            if ready.exists():
                try:
                    os.killpg(int(ready.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_unicode_line_separator_in_branch_is_preserved(self):
        name = "feature\u2028separator"
        self.git("branch", "-m", name)
        self.git("branch", "retained")
        self.git("branch", "--set-upstream-to=retained", name)
        row = self.scan()[0]
        self.assertEqual(row["branch"], name)
        self.assertEqual(row["sync"], "equal")


if __name__ == "__main__":
    unittest.main()
