"""Local paste entry. No HTTP listener, no cookies in process arguments or public pages."""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    win = tk.Tk()
    win.title("企业调研 · 小红书登录与续查")
    win.geometry("820x690")
    win.minsize(670, 540)
    win.columnconfigure(0, weight=1)
    win.rowconfigure(2, weight=1)
    win.rowconfigure(5, weight=1)
    heading = ttk.Frame(win, padding=16)
    heading.grid(row=0, column=0, sticky="ew")
    ttk.Label(heading, text="粘贴新的 cURL，继续未完成的企业调研", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w")
    ttk.Label(heading, text="登录信息在本机加密保存；查询失败会保留进度。当前评分由对话助手审阅资料后填写。").pack(anchor="w", pady=(8,0))
    company_row = ttk.Frame(heading)
    company_row.pack(fill='x', pady=(10,0))
    ttk.Label(company_row, text='指定企业（留空续查列表）：').pack(side='left')
    company_name = tk.StringVar()
    ttk.Entry(company_row, textvariable=company_name).pack(side='left', fill='x', expand=True)
    ttk.Label(win, text="小红书搜索请求（支持 Windows / bash 的 Copy as cURL）").grid(row=1, column=0, sticky="w", padx=16)
    curl_box = tk.Text(win, height=10, wrap="word", font=("Consolas", 10))
    curl_box.grid(row=2, column=0, sticky="nsew", padx=16, pady=8)
    controls = ttk.Frame(win, padding=(16, 4))
    controls.grid(row=3, column=0, sticky="ew")
    ttk.Label(controls, text="本批企业数：").pack(side="left")
    limit = tk.IntVar(value=2)
    ttk.Spinbox(controls, from_=1, to=900, increment=3, width=6, textvariable=limit).pack(side="left")
    ttk.Label(controls, text="  每家最多3篇正文及部分公开评论，分别审阅3个维度。").pack(side="left")
    buttons = ttk.Frame(win, padding=(16,8))
    buttons.grid(row=4, column=0, sticky="ew")
    messages = tk.Text(win, height=10, state="disabled", wrap="word", font=("Microsoft YaHei", 10))
    messages.grid(row=5, column=0, sticky="nsew", padx=16, pady=(0,16))
    output = queue.Queue()
    job = {"process": None, "busy": False}

    def log(text):
        messages.configure(state="normal")
        messages.insert("end", text + "\n")
        messages.see("end")
        messages.configure(state="disabled")

    def start(import_new=False, status=False):
        if job["busy"]:
            return
        try:
            amount = int(limit.get())
            if not 1 <= amount <= 900:
                raise ValueError()
        except (ValueError, tk.TclError):
            messagebox.showerror("批量大小", "请输入1–900之间的企业数。")
            return
        payload = curl_box.get("1.0", "end").strip() if import_new else None
        if import_new and not payload:
            messagebox.showinfo("还没有请求", "先把新的小红书搜索cURL粘贴到上面的文本框。")
            return
        console_python = Path(sys.executable).with_name('python.exe') if sys.platform == 'win32' else Path(sys.executable)
        args = [str(console_python), "-X", "utf8", str(ROOT / "xhs_research.py")]
        if status:
            args += ["status"]
        elif import_new:
            args += ["import-curl", "--stdin", "--run", "--limit", str(amount)]
        else:
            args += ["run", "--limit", str(amount)]
        if not status:
            args += ['--by-company','--comments']
        if not status and company_name.get().strip():
            args += ['--company', company_name.get().strip()]
        job["busy"] = True
        for button in (import_btn, resume_btn, status_btn):
            button.configure(state="disabled")
        # Remove plaintext from the window immediately; worker owns stdin copy only.
        if import_new:
            curl_box.delete("1.0", "end")
        log("开始检查登录信息与任务进度…" if import_new else "读取任务进度…")

        def work():
            try:
                proc = subprocess.Popen(args, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                job["process"] = proc
                if payload:
                    proc.stdin.write(payload)
                proc.stdin.close()
                for line in proc.stdout:
                    output.put(("line", line.rstrip()))
                proc.wait()
                output.put(("done", proc.returncode))
            except Exception:
                output.put(("line", "启动失败，请检查本机Python环境；未记录登录内容。"))
                output.put(("done", 2))
        threading.Thread(target=work, daemon=True).start()

    def stop():
        proc = job["process"]
        if proc and proc.poll() is None:
            proc.terminate()
            log("已停止当前批次；已完成笔记会保留，下次从未完成维度继续。")

    import_btn = ttk.Button(buttons, text="导入并继续查询", command=lambda: start(import_new=True))
    import_btn.pack(side="left", padx=(0,8))
    resume_btn = ttk.Button(buttons, text="使用已保存登录信息续查", command=start)
    resume_btn.pack(side="left", padx=(0,8))
    status_btn = ttk.Button(buttons, text="查看进度", command=lambda: start(status=True))
    status_btn.pack(side="left", padx=(0,8))
    ttk.Button(buttons, text="停止", command=stop).pack(side="left")

    def poll():
        try:
            while True:
                kind, value = output.get_nowait()
                if kind == "line":
                    log(value)
                else:
                    job.update(process=None, busy=False)
                    for button in (import_btn, resume_btn, status_btn):
                        button.configure(state="normal")
                    log("本批完成。资料待评估，可继续下一批。" if value == 0 else "已暂停。若提示登录/验证失败，请在小红书处理后粘贴新请求。")
        except queue.Empty:
            pass
        win.after(150, poll)

    def close():
        stop()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", close)
    poll()
    start(status=True)
    win.mainloop()


if __name__ == "__main__":
    main()
