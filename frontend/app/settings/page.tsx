import { LogoutButton } from "../../components/LogoutButton";

export default function SettingsPage() {
  return (
    <main className="mx-auto w-full max-w-[1360px] space-y-6 p-8 xl:p-10">
      <section className="rounded-xl border border-neutral-800 bg-neutral-900 p-6">
        <h2 className="text-xl font-semibold tracking-tight text-neutral-100">Session</h2>
        <p className="mt-2 max-w-xl text-sm leading-6 text-neutral-400">
          End this session on this device. You will need to enter your PIN to access your account again.
        </p>
        <div className="mt-5">
          <LogoutButton />
        </div>
      </section>
    </main>
  );
}
