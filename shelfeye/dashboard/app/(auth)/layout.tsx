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
          <div className="preview-card" aria-hidden="true">
            <div className="preview-row"><strong>Paracetamol 500mg</strong><span className="pill ok">In stock</span></div>
            <div className="preview-row"><strong>Ibuprofen 400mg</strong><span className="pill low">Low</span></div>
            <div className="preview-row"><strong>Amoxicillin 250mg</strong><span className="pill out">Out of stock</span></div>
          </div>
        </div>

        <div className="auth-foot">© {new Date().getFullYear()} ShelfEye</div>
      </aside>

      <main className="auth-form-wrap">{children}</main>
    </div>
  );
}
