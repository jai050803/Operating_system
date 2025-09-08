#!/usr/bin/env python3
"""
process_demo.py

Usage examples:
  python3 process_demo.py --task 1 --n 4
  python3 process_demo.py --task 2 --n 3 --cmd "ls"  # children exec 'ls'
  python3 process_demo.py --task 3 --mode zombie
  python3 process_demo.py --task 3 --mode orphan
  python3 process_demo.py --task 4 --pid 1234
  python3 process_demo.py --task 5 --n 4

Note: run on Linux. Lowering nice (making priority higher) may require root.
"""
import os
import sys
import argparse
import time
import subprocess
from pathlib import Path

def task1_create_children(n: int):
    """Task 1: Create N children using fork; each prints PID, PPID, message.
       Parent waits for all children using os.wait().
    """
    children = []
    print(f"[PARENT {os.getpid()}] Starting: creating {n} children")
    for i in range(n):
        pid = os.fork()
        if pid == 0:
            # Child
            print(f"[CHILD {os.getpid()}] parent={os.getppid()} message='Hello from child {i}'")
            os._exit(0)  # immediate exit from child
        else:
            children.append(pid)

    # Parent waits for all children
    for _ in children:
        waited_pid, status = os.wait()
        print(f"[PARENT {os.getpid()}] Reaped child {waited_pid} status={status}")
    print(f"[PARENT {os.getpid()}] All children reaped. Done.")

def task2_exec_children(n: int, cmd: str, use_exec: bool = True):
    """
    Task 2: Each child executes a Linux command.
    If use_exec True -> os.execvp() in child (replaces child process).
    Else -> subprocess.run() inside child (keeps Python wrapper).
    """
    print(f"[PARENT {os.getpid()}] Creating {n} children to run: {cmd} (use_exec={use_exec})")
    children = []
    for i in range(n):
        pid = os.fork()
        if pid == 0:
            # Child process
            print(f"[CHILD {os.getpid()}] parent={os.getppid()} executing '{cmd}'")
            if use_exec:
                # execvp replaces the Python process with the program
                args = cmd.split()
                try:
                    os.execvp(args[0], args)
                except FileNotFoundError:
                    print(f"[CHILD {os.getpid()}] exec failed: {args[0]} not found", file=sys.stderr)
                    os._exit(1)
            else:
                # Use subprocess.run to execute command and return control to Python child
                try:
                    subprocess.run(cmd, shell=True, check=False)
                except Exception as e:
                    print(f"[CHILD {os.getpid()}] subprocess error: {e}", file=sys.stderr)
                os._exit(0)
        else:
            children.append(pid)

    # Parent waits
    for _ in children:
        wpid, status = os.wait()
        print(f"[PARENT {os.getpid()}] Reaped child {wpid} status={status}")
    print("[PARENT] Task 2 complete.")

def task3_zombie_or_orphan(mode: str):
    """
    Task 3: Demonstrate zombie and orphan.

    Zombie: Parent doesn't wait; child exits quickly -> becomes defunct until parent reaps.
      - We fork: child exits (becomes defunct). Parent sleeps (so child remains defunct).
      - Use: `ps -el | grep defunct` externally to observe.

    Orphan: Parent exits before child finishes; child is adopted by init/systemd (PID 1).
      - We fork: parent exits immediately, child keeps running.
    """
    print(f"[PID {os.getpid()}] Running Task3 mode={mode}. Note: run on Linux and use another terminal to `ps -el | grep defunct`")

    pid = os.fork()
    if pid == 0:
        # child
        if mode == "zombie":
            print(f"[CHILD {os.getpid()}] exiting immediately (will become zombie if parent doesn't wait)")
            os._exit(0)
        elif mode == "orphan":
            print(f"[CHILD {os.getpid()}] running for 10s to show orphanhood; parent should exit")
            for i in range(10):
                print(f"[CHILD {os.getpid()}] working... {i+1}/10 parent now: {os.getppid()}")
                time.sleep(1)
            print(f"[CHILD {os.getpid()}] done; parent now {os.getppid()}")
            os._exit(0)
        else:
            print("[CHILD] unknown mode")
            os._exit(1)
    else:
        # parent
        if mode == "zombie":
            print(f"[PARENT {os.getpid()}] child {pid} created and will be left to become zombie. Sleeping 15s (do NOT wait).")
            time.sleep(15)
            print(f"[PARENT {os.getpid()}] Now reaping child {pid} with wait()")
            try:
                wpid, status = os.waitpid(pid, 0)
                print(f"[PARENT {os.getpid()}] Reaped {wpid} status={status}")
            except ChildProcessError:
                print("[PARENT] no child to wait for")
        elif mode == "orphan":
            print(f"[PARENT {os.getpid()}] Exiting immediately; child {pid} runs on.")
            # parent exits without waiting -> child becomes orphan and adopted by init/systemd
            os._exit(0)
        else:
            print("[PARENT] unknown mode")
            os._exit(1)

def task4_inspect_proc(pid: int):
    """
    Task 4: Read /proc/[pid]/status, exe, fd
    """
    base = Path(f"/proc/{pid}")
    if not base.exists():
        print(f"/proc/{pid} does not exist. Is the PID valid and are you on Linux?")
        return

    # status
    status_file = base / "status"
    print(f"--- /proc/{pid}/status ---")
    try:
        with status_file.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                # we print only a few important fields to keep output tidy
                if line.startswith(("Name:", "State:", "VmSize:", "VmRSS:", "VmPeak:", "VmData:", "VmSwap:")):
                    print(line.strip())
    except Exception as e:
        print("Couldn't read status:", e)

    # exe
    exe_link = base / "exe"
    print(f"\n--- /proc/{pid}/exe (executable path) ---")
    try:
        path = os.readlink(str(exe_link))
        print(path)
    except Exception as e:
        print("Couldn't read exe link:", e)

    # fds
    fd_dir = base / "fd"
    print(f"\n--- /proc/{pid}/fd (open file descriptors) ---")
    if fd_dir.exists():
        for fd in sorted(fd_dir.iterdir(), key=lambda p: int(p.name)):
            try:
                target = os.readlink(str(fd))
            except Exception as e:
                target = f"(error: {e})"
            print(f"fd {fd.name} -> {target}")
    else:
        print("No fd directory available (or insufficient permissions).")

def cpu_work(iterations: int = 50_000_00):
    """CPU-intensive work: simple busy loop that does some math."""
    s = 0
    for i in range(1, iterations):
        s += (i * i) % (i + 1)
    return s

def task5_prioritization(n: int):
    """
    Task 5: Spawn n CPU-bound children, assign different nice() values,
    measure completion time and print order.

    Note: os.nice() in child changes child's niceness relative to current.
    Only increases (makes lower priority) reliably for normal users.
    Decreasing nice (raising priority) requires root.
    """
    print(f"[PARENT {os.getpid()}] Spawning {n} CPU-bound children with varied nice()")
    children = []
    results = []

    for i in range(n):
        pid = os.fork()
        if pid == 0:
            # child: set niceness, run CPU task and record duration
            nice_offset = i * 5  # 0,5,10,...
            try:
                os.nice(nice_offset)  # increase niceness (lower priority)
            except OSError as e:
                print(f"[CHILD {os.getpid()}] unable to set nice: {e}")
            start = time.monotonic()
            # smaller iteration count for demo speed
            work_result = cpu_work(iterations=500000)
            duration = time.monotonic() - start
            print(f"[CHILD {os.getpid()}] nice_offset={nice_offset} duration={duration:.3f}s done")
            # write a small result file (parent will read) - safer than pipes across forks
            with open(f"/tmp/process_demo_child_{os.getpid()}.txt", "w") as f:
                f.write(f"{os.getpid()},{nice_offset},{duration:.6f}\n")
            os._exit(0)
        else:
            children.append(pid)

    # Parent waits and collects results
    for _ in children:
        wpid, status = os.wait()
        print(f"[PARENT] Reaped child {wpid} status={status}")
    # Read results
    print("\nResults (collected from /tmp files):")
    entries = []
    for pid in children:
        pfile = Path(f"/tmp/process_demo_child_{pid}.txt")
        if pfile.exists():
            txt = pfile.read_text().strip()
            try:
                pid_s, nice_s, dur_s = txt.split(",")
                entries.append((int(pid_s), int(nice_s), float(dur_s)))
            except Exception:
                print("Malformed result file for", pid)
            # clean up
            try:
                pfile.unlink()
            except Exception:
                pass
    # sort by completion duration
    entries.sort(key=lambda x: x[2])
    print("PID\tNice\tDuration(s)  (lower duration -> finished earlier)")
    for pid_s, nice_s, dur_s in entries:
        print(f"{pid_s}\t{nice_s}\t{dur_s:.3f}")
    print("\nInterpretation: children with lower priority (higher nice offset) typically finish later — but scheduler, CPU contention and I/O can affect results.")

def main():
    parser = argparse.ArgumentParser(description="Process demo tasks (Linux).")
    parser.add_argument("--task", type=int, required=True, choices=[1,2,3,4,5], help="Task number to run")
    parser.add_argument("--n", type=int, default=3, help="Number of children")
    parser.add_argument("--cmd", type=str, default="ls -l", help="Command for Task 2")
    parser.add_argument("--use-exec", action="store_true", help="Task 2: use execvp instead of subprocess")
    parser.add_argument("--mode", type=str, choices=["zombie","orphan"], help="Task 3 mode")
    parser.add_argument("--pid", type=int, help="PID for Task 4")
    args = parser.parse_args()

    if os.name != "posix":
        print("This script requires a POSIX system (Linux).")
        sys.exit(1)

    if args.task == 1:
        task1_create_children(args.n)
    elif args.task == 2:
        task2_exec_children(args.n, args.cmd, use_exec=args.use_exec)
    elif args.task == 3:
        if not args.mode:
            print("Task 3 requires --mode zombie|orphan")
            sys.exit(1)
        task3_zombie_or_orphan(args.mode)
    elif args.task == 4:
        if not args.pid:
            print("Task 4 requires --pid PID")
            sys.exit(1)
        task4_inspect_proc(args.pid)
    elif args.task == 5:
        task5_prioritization(args.n)

if __name__ == "__main__":
    main()
