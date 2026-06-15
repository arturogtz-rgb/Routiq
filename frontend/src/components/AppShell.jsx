import { NavLink, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import Logo from '@/components/Logo';
import NotificationBell from '@/components/NotificationBell';
import api from '@/lib/api';
import {
  LayoutDashboard, Kanban, FileText, Package, Users, Settings, MessageCircle, LogOut, Menu, X, ChevronRight, Sparkles,
} from 'lucide-react';

const NAV_BY_ROLE = {
  company_admin: [
    { to: '/app/dashboard', label: 'Dashboard', icon: LayoutDashboard, testid: 'nav-dashboard' },
    { to: '/app/kanban', label: 'Pipeline', icon: Kanban, testid: 'nav-kanban' },
    { to: '/app/quotations', label: 'Cotizaciones', icon: FileText, testid: 'nav-quotations' },
    { to: '/app/packages', label: 'Paquetes', icon: Package, testid: 'nav-packages' },
    { to: '/app/services', label: 'Servicios', icon: Sparkles, testid: 'nav-services' },
    { to: '/app/whatsapp', label: 'WhatsApp', icon: MessageCircle, testid: 'nav-whatsapp' },
    { to: '/app/team', label: 'Equipo', icon: Users, testid: 'nav-team' },
    { to: '/app/settings', label: 'Ajustes', icon: Settings, testid: 'nav-settings' },
  ],
  executive: [
    { to: '/app/dashboard', label: 'Dashboard', icon: LayoutDashboard, testid: 'nav-dashboard' },
    { to: '/app/kanban', label: 'Pipeline', icon: Kanban, testid: 'nav-kanban' },
    { to: '/app/quotations', label: 'Cotizaciones', icon: FileText, testid: 'nav-quotations' },
    { to: '/app/packages', label: 'Paquetes', icon: Package, testid: 'nav-packages' },
    { to: '/app/services', label: 'Servicios', icon: Sparkles, testid: 'nav-services' },
    { to: '/app/whatsapp', label: 'WhatsApp', icon: MessageCircle, testid: 'nav-whatsapp' },
  ],
  super_admin: [
    { to: '/master', label: 'Panel Master', icon: LayoutDashboard, testid: 'nav-master' },
    { to: '/master/companies', label: 'Empresas', icon: Users, testid: 'nav-companies' },
  ],
};

function CompanyBrand({ size = 30 }) {
  const { user } = useAuth();
  const [company, setCompany] = useState(null);
  useEffect(() => {
    if (user?.tenant_id) {
      api.get('/companies/me').then(({ data }) => setCompany(data)).catch(() => null);
    }
  }, [user]);
  const logo = company?.logo_url;
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  if (logo) {
    return (
      <div className="inline-flex items-center gap-2.5" data-testid="company-brand">
        <img src={`${backend}${logo}`} alt={company?.name || 'Logo'} style={{ height: size, width: 'auto', maxWidth: size * 2.5, objectFit: 'contain' }} />
        <span className="font-display font-semibold text-ink-900 text-base hidden sm:inline">{company?.name}</span>
      </div>
    );
  }
  return <Logo size={size} />;
}

export default function AppShell({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const items = NAV_BY_ROLE[user?.role] || [];

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-cream flex">
      {/* Sidebar (desktop) */}
      <aside className="hidden md:flex w-64 shrink-0 border-r border-ink-100 bg-white flex-col">
        <div className="px-6 py-5 border-b border-ink-100 flex items-center justify-between">
          <CompanyBrand size={30} />
          {user?.tenant_id && <NotificationBell />}
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {items.map(({ to, label, icon: Icon, testid }) => (
            <NavLink key={to} to={to} end={to === '/master'} data-testid={testid}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  isActive ? 'bg-brand-50 text-brand-500' : 'text-ink-500 hover:bg-brand-50/60 hover:text-brand-500'
                }`
              }>
              <Icon className="w-[18px] h-[18px]" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-ink-100">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-full bg-brand-500 text-white flex items-center justify-center font-display font-semibold">
              {(user?.name || 'U').slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink-900 truncate">{user?.name}</p>
              <p className="text-xs text-ink-400 truncate">{user?.email}</p>
            </div>
          </div>
          <button onClick={handleLogout} data-testid="logout-btn" className="btn-ghost w-full justify-center text-sm">
            <LogOut className="w-4 h-4" /> Cerrar sesión
          </button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 z-40 bg-white/90 backdrop-blur-xl border-b border-ink-100">
        <div className="flex items-center justify-between px-4 h-14">
          <button onClick={() => setMobileOpen(true)} data-testid="open-mobile-menu" className="p-2 rounded-lg text-ink-700 hover:bg-brand-50">
            <Menu className="w-5 h-5" />
          </button>
          <Logo size={26} />
          <div className="flex items-center gap-1">
            {user?.tenant_id && <NotificationBell />}
            <button onClick={handleLogout} data-testid="mobile-logout-btn" className="p-2 rounded-lg text-ink-700 hover:bg-brand-50">
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50" role="dialog">
          <div className="absolute inset-0 bg-ink-900/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-72 bg-white shadow-2xl animate-fade-up flex flex-col">
            <div className="px-5 py-4 border-b border-ink-100 flex items-center justify-between">
              <Logo size={28} />
              <button onClick={() => setMobileOpen(false)} className="p-2 rounded-lg hover:bg-brand-50" data-testid="close-mobile-menu">
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="flex-1 px-3 py-4 space-y-1">
              {items.map(({ to, label, icon: Icon, testid }) => (
                <NavLink key={to} to={to} end={to === '/master'} onClick={() => setMobileOpen(false)} data-testid={`m-${testid}`}
                  className={({ isActive }) =>
                    `flex items-center justify-between gap-3 px-3 py-3 rounded-xl text-base font-medium ${
                      isActive ? 'bg-brand-50 text-brand-500' : 'text-ink-700 hover:bg-brand-50'
                    }`
                  }>
                  <span className="flex items-center gap-3"><Icon className="w-5 h-5" />{label}</span>
                  <ChevronRight className="w-4 h-4 opacity-40" />
                </NavLink>
              ))}
            </nav>
            <div className="p-4 border-t border-ink-100 text-sm text-ink-500">
              <p className="font-semibold text-ink-900">{user?.name}</p>
              <p className="text-xs text-ink-400">{user?.email}</p>
            </div>
          </aside>
        </div>
      )}

      {/* Main */}
      <main className="flex-1 min-w-0 pt-14 md:pt-0">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8 py-6 md:py-10">
          {children}
        </div>
      </main>
    </div>
  );
}
