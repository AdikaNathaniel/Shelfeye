import { ActivityIcon, AlertIcon, CameraIcon, Logo } from "@/components/Icons";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth">
      <aside className="auth-panel">
        <div className="brand">
          <Logo />
          <div>
            <div className="brand-name">ShelfEye</div>
            <div className="brand-sub">Smart shelf counting</div>
          </div>
        </div>

        <div className="auth-pitch">
          <h2>Know what&apos;s on your shelves without counting.</h2>
          <p>Small cameras watch each shelf, count the stock and tell you the moment something runs low.</p>
          <ul className="features">
            <li><span><CameraIcon size={16} /></span>Automatic counts from every shelf</li>
            <li><span><AlertIcon size={16} /></span>Low-stock alerts before you run out</li>
            <li><span><ActivityIcon size={16} /></span>A record of every item taken</li>
          </ul>
        </div>

        <div className="auth-foot">© {new Date().getFullYear()} ShelfEye</div>
      </aside>

      <main className="auth-form-wrap">{children}</main>
    </div>
  );
}
