"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function Nav() {
  const { user, logout } = useAuth();
  const router = useRouter();

  function handleLogout() {
    logout();
    router.push("/");
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="text-lg font-semibold text-slate-900">
          Sentra
        </Link>
        <div className="flex items-center gap-6 text-sm">
          {user ? (
            <>
              <Link href="/dashboard" className="text-slate-600 hover:text-slate-900">
                Dashboard
              </Link>
              <Link href="/audit-log" className="text-slate-600 hover:text-slate-900">
                Audit log
              </Link>
              <span className="text-slate-400">{user.email}</span>
              <button
                onClick={handleLogout}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50"
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="text-slate-600 hover:text-slate-900">
                Sign in
              </Link>
              <Link
                href="/register"
                className="rounded-md bg-slate-900 px-3 py-1.5 text-white hover:bg-slate-700"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
