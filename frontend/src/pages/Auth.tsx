import { useState, type FormEvent } from "react";
import { api } from "../api";

export default function AuthPage({ onAuthenticated }: { onAuthenticated: (token: string) => void }) {
  const [isSignup, setIsSignup] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (isSignup && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const result = isSignup
        ? await api.signup(email, password)
        : await api.login(email, password);
      onAuthenticated(result.access_token);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-full place-items-center px-4 py-12">
      <section className="glass w-full max-w-md p-8 sm:p-10">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-5 grid h-12 w-12 place-items-center rounded-2xl text-xl font-extrabold text-white"
            style={{ background: "linear-gradient(160deg,#8f8cf5,#4f4fc9)" }}>L</div>
          <p className="text-sm font-bold uppercase tracking-[.18em] text-iris-deep">Legacy Code Intelligence</p>
          <h1 className="mt-3 text-2xl font-extrabold text-ink">{isSignup ? "Create your account" : "Welcome back"}</h1>
          <p className="mt-2 text-sm text-slate-500">
            {isSignup ? "Sign up to explore and analyze codebases." : "Sign in to continue to your workspace."}
          </p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="block space-y-1.5 text-sm font-semibold text-slate-700">
            Email
            <input className="input" type="email" autoComplete="email" required maxLength={254}
              value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label className="block space-y-1.5 text-sm font-semibold text-slate-700">
            Password
            <input className="input" type="password" autoComplete={isSignup ? "new-password" : "current-password"}
              required minLength={8} maxLength={128} value={password}
              onChange={(event) => setPassword(event.target.value)} />
          </label>
          {isSignup && (
            <label className="block space-y-1.5 text-sm font-semibold text-slate-700">
              Confirm password
              <input className="input" type="password" autoComplete="new-password" required minLength={8}
                maxLength={128} value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)} />
            </label>
          )}
          {error && <p role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
          <button className="btn-primary w-full py-3" type="submit" disabled={busy}>
            {busy ? "Please wait…" : isSignup ? "Create account" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          {isSignup ? "Already have an account?" : "New to Legacy Code Intelligence?"}{" "}
          <button type="button" className="font-bold text-iris-deep hover:underline"
            onClick={() => { setIsSignup(!isSignup); setError(null); }}>
            {isSignup ? "Sign in" : "Create an account"}
          </button>
        </p>
      </section>
    </main>
  );
}
