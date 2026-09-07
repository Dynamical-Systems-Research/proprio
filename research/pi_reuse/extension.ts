import { spawn } from "node:child_process";
import { existsSync, realpathSync, statSync, writeFileSync, renameSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import { Type } from "@earendil-works/pi-ai";
import { createBashTool, type BashOperations, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  const required = (name: string) => {
    const value = process.env[name];
    if (!value) throw new Error(`Missing ${name}`);
    return realpathSync(value);
  };
  const workspace = required("PROPRIO_WORKSPACE");
  const runDir = required("PROPRIO_RUN_DIR");
  const root = required("PROPRIO_ROOT");
  const runner = required("PROPRIO_RUNNER");
  const numberSetting = (name: string, fallback: number, maximum: number, integer = true) => {
    const value = Number(process.env[name] ?? fallback);
    if (!Number.isFinite(value) || value <= 0 || value > maximum || (integer && !Number.isInteger(value))) {
      throw new Error(`Invalid ${name}`);
    }
    return value;
  };
  const executionLimit = numberSetting("PROPRIO_EXECUTION_LIMIT", 2, 6);
  const messageLimit = numberSetting("PROPRIO_MAX_MESSAGES", 24, 24);
  const outputLimit = numberSetting("PROPRIO_MAX_OUTPUT_TOKENS", 65536, 65536);
  const costLimit = numberSetting("PROPRIO_SESSION_COST", 0.5, 1, false);
  const authorOnly = process.env.PROPRIO_AUTHOR_ONLY === "1";
  let executions = 0;
  let ready = false;
  let messages = 0;
  let tokens = 0;
  let cost = 0;
  let stopped = false;
  const saveUsage = () => {
    const path = resolve(runDir, "usage.json");
    writeFileSync(`${path}.tmp`, JSON.stringify({ messages, tokens, cost_usd: cost,
      execute_calls: executions, stopped_by_budget: stopped }) + "\n", { mode: 0o600 });
    renameSync(`${path}.tmp`, path);
  };
  const sandboxArgs = (command: string) => {
    const args = ["--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
      "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
      "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin",
      "--ro-bind", "/lib", "/lib"];
    if (existsSync("/lib64")) args.push("--ro-bind", "/lib64", "/lib64");
    if (existsSync("/etc/ld.so.cache")) args.push("--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache");
    args.push("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
      "--bind", workspace, "/workspace");
    if (workspace !== "/workspace") args.push("--bind", workspace, workspace);
    args.push("--chdir", "/workspace", "/bin/bash", "-c", command);
    return args;
  };
  const operations: BashOperations = {
    async exec(command, _cwd, { onData, signal, timeout }) {
      return new Promise((accept, reject) => {
        const child = spawn("bwrap", sandboxArgs(command), { env: { PATH: "/usr/bin:/bin" },
          detached: true, stdio: ["ignore", "pipe", "pipe"] });
        let timedOut = false;
        const kill = () => {
          if (child.pid) { try { process.kill(-child.pid, "SIGKILL"); } catch { child.kill("SIGKILL"); } }
        };
        const timer = setTimeout(() => { timedOut = true; kill(); }, Math.min(timeout || 60, 60) * 1000);
        signal?.addEventListener("abort", kill, { once: true });
        if (signal?.aborted) kill();
        child.stdout.on("data", onData);
        child.stderr.on("data", onData);
        const cleanup = () => { clearTimeout(timer); signal?.removeEventListener("abort", kill); };
        child.on("error", error => { cleanup(); reject(error); });
        child.on("close", code => {
          cleanup();
          if (signal?.aborted || timedOut) reject(new Error(timedOut ? "Tool timed out" : "Aborted"));
          else accept({ exitCode: code });
        });
      });
    },
  };
  const bash = createBashTool("/workspace", { operations });
  pi.registerTool({ ...bash, async execute(id, params, signal, onUpdate) {
    if (!ready || stopped) throw new Error("Sandbox not ready or session budget exhausted");
    return bash.execute(id, params, signal, onUpdate);
  } });
  pi.on("session_start", async () => {
    const probe = await operations.exec("true", "/workspace", { onData() {}, timeout: 10 });
    if (probe.exitCode !== 0) throw new Error("Sandbox initialization failed");
    ready = true;
    saveUsage();
  });
  if (!authorOnly) pi.registerTool({
    name: "execute_candidate", label: "Execute candidate",
    description: `Execute a procedure file in the instrument simulator and receive visible feedback. At most ${executionLimit} calls are allowed.`,
    parameters: Type.Object({ path: Type.String({ description: "Procedure file under /workspace" }) }),
    async execute(_id, params, signal) {
      if (!ready || stopped || executions >= executionLimit) throw new Error("Execution unavailable or limit reached");
      const local = params.path.startsWith("/workspace/") ? params.path.slice(11) : params.path;
      const candidate = realpathSync(resolve(workspace, local));
      const rel = relative(workspace, candidate);
      if (rel === ".." || rel.startsWith("../") || isAbsolute(rel)) throw new Error("Candidate outside workspace");
      const stat = statSync(candidate);
      if (!stat.isFile() || stat.size > 16384) throw new Error("Candidate must be a regular file of at most 16384 bytes");
      executions++;
      saveUsage();
      const output = await new Promise<string>((accept, reject) => {
        const child = spawn(resolve(root, ".venv/bin/python"),
          [runner, "execute", runDir, candidate],
          { cwd: root, env: { PATH: "/usr/bin:/bin", LANG: "C.UTF-8" },
            stdio: ["ignore", "pipe", "pipe"], signal });
        let stdout = "";
        child.stdout.on("data", chunk => { stdout += chunk; if (stdout.length > 65536) child.kill("SIGKILL"); });
        child.stderr.resume();
        child.on("error", reject);
        child.on("close", code => code === 0 ? accept(stdout) : reject(new Error("Simulator execution failed; private receipt retained")));
      });
      const result = JSON.parse(output);
      return { content: [{ type: "text", text: JSON.stringify(result) }], details: {} };
    },
  });
  pi.on("before_provider_request", (event) => {
    if (stopped) throw new Error("Session budget exhausted");
    if (existsSync(resolve(runDir, "evaluator-failure.json"))) throw new Error("Evaluator unavailable; study stopped");
    const payload = { ...(event.payload as Record<string, unknown>) };
    delete payload.temperature;
    if ("max_output_tokens" in payload) payload.max_output_tokens = outputLimit;
    else if ("max_completion_tokens" in payload) payload.max_completion_tokens = outputLimit;
    else payload.max_tokens = outputLimit;
    return payload;
  });
  pi.on("message_end", (event, ctx) => {
    if (event.message.role !== "assistant") return;
    const usage = event.message.usage;
    messages++;
    tokens += usage?.totalTokens ?? 0;
    cost += usage?.cost?.total ?? 0;
    stopped = messages >= messageLimit || cost >= costLimit;
    saveUsage();
    if (stopped) ctx.abort();
  });
}
