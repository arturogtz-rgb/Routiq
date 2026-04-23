import { Link } from 'react-router-dom';
import Logo from '@/components/Logo';
import {
  MessageCircle, Kanban, FileText, Calculator, Sparkles, Smartphone, Shield, Zap, ArrowRight, Check,
} from 'lucide-react';

const HERO_IMG = 'https://images.unsplash.com/photo-1745936720392-20a9af92a025?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NjZ8MHwxfHNlYXJjaHwyfHxhZ2F2ZSUyMGZpZWxkJTIwbGFuZHNjYXBlJTIwamFsaXNjb3xlbnwwfHx8fDE3NzY5ODQyNzN8MA&ixlib=rb-4.1.0&q=85';
const FEATURE_IMG = 'https://images.unsplash.com/photo-1758518729685-f88df7890776?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxODd8MHwxfHNlYXJjaHwzfHxwcm9mZXNzaW9uYWwlMjBidXNpbmVzcyUyMG1lZXRpbmclMjBvZmZpY2V8ZW58MHx8fHwxNzc2OTg0MjczfDA&ixlib=rb-4.1.0&q=85';

function NavBar() {
  return (
    <header className="sticky top-0 z-40 backdrop-blur-xl bg-white/80 border-b border-ink-100/60">
      <div className="max-w-7xl mx-auto px-4 md:px-8 h-16 flex items-center justify-between">
        <Logo size={28} />
        <nav className="hidden md:flex items-center gap-7 text-sm font-medium text-ink-700">
          <a href="#features" className="hover:text-brand-500 transition-colors">Producto</a>
          <a href="#how" className="hover:text-brand-500 transition-colors">Cómo funciona</a>
          <a href="#pricing" className="hover:text-brand-500 transition-colors">Planes</a>
        </nav>
        <div className="flex items-center gap-3">
          <Link to="/login" className="btn-ghost text-sm" data-testid="nav-login-link">Entrar</Link>
          <a href="#demo" className="btn-primary text-sm hidden sm:inline-flex" data-testid="nav-cta-demo">
            Pedir demo <ArrowRight className="w-4 h-4" />
          </a>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <img src={HERO_IMG} alt="" className="absolute inset-0 w-full h-full object-cover opacity-30" />
      <div className="absolute inset-0 bg-gradient-to-br from-cream/95 via-cream/80 to-brand-50/90" />
      <div className="relative max-w-7xl mx-auto px-4 md:px-8 py-20 md:py-28 grid md:grid-cols-12 gap-10 items-center">
        <div className="md:col-span-7 space-y-6 animate-fade-up">
          <span className="pill bg-brand-50 text-brand-500" data-testid="hero-pill">
            <Sparkles className="w-3.5 h-3.5" /> Cotiza, da seguimiento y cierra — sin perderte en WhatsApp
          </span>
          <h1 className="font-display text-4xl sm:text-5xl lg:text-[64px] leading-[1.02] font-bold text-ink-900 tracking-tight">
            La memoria operativa <br />
            de tu <span className="text-brand-500">tour operador</span>.
          </h1>
          <p className="text-lg text-ink-500 max-w-xl leading-relaxed">
            Routiq convierte tus chats de WhatsApp en cotizaciones estructuradas, con pipeline visual, PDF profesional
            y un motor de precios 100% configurable. Hecho para DMCs y operadores receptivos en Latinoamérica.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link to="/login" className="btn-primary" data-testid="hero-cta-primary">
              Empezar ahora <ArrowRight className="w-4 h-4" />
            </Link>
            <a href="#features" className="btn-secondary" data-testid="hero-cta-secondary">
              Ver características
            </a>
          </div>
          <div className="flex items-center gap-4 pt-4 text-sm text-ink-500">
            <div className="flex -space-x-2">
              {['#185FA5', '#378ADD', '#E1F5EE', '#FAEEDA'].map((c, i) => (
                <div key={i} className="w-8 h-8 rounded-full border-2 border-white" style={{ background: c }} />
              ))}
            </div>
            <span><b className="text-ink-900">+30 tour operadores</b> ya en lista de espera</span>
          </div>
        </div>
        <div className="md:col-span-5">
          <MockDashboardCard />
        </div>
      </div>
    </section>
  );
}

function MockDashboardCard() {
  return (
    <div className="relative">
      <div className="absolute -inset-4 bg-gradient-to-br from-brand-400/30 to-mint-200/50 rounded-[28px] blur-2xl" />
      <div className="relative card-surface p-5 md:p-6 space-y-4 animate-fade-up" style={{ animationDelay: '0.15s' }}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase font-bold tracking-widest text-ink-400">Pipeline</p>
            <p className="font-display text-xl font-semibold">Cotizaciones activas</p>
          </div>
          <span className="pill bg-mint-100 text-emerald-700">+24% vs. mes pasado</span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: 'Nuevas', n: 12, tone: 'bg-ink-100 text-ink-700' },
            { label: 'Cotizando', n: 8, tone: 'bg-brand-50 text-brand-500' },
            { label: 'Enviadas', n: 5, tone: 'bg-peach-100 text-amber-700' },
          ].map((c) => (
            <div key={c.label} className="rounded-xl border border-ink-100 p-3">
              <p className="text-[11px] uppercase font-bold tracking-wider text-ink-400">{c.label}</p>
              <p className="font-display font-bold text-2xl text-ink-900">{c.n}</p>
              <span className={`pill mt-2 ${c.tone}`}>activas</span>
            </div>
          ))}
        </div>
        <div className="rounded-xl bg-gradient-to-r from-brand-500 to-accent p-4 text-white">
          <p className="text-[11px] uppercase font-bold tracking-widest opacity-80">Proyección del mes</p>
          <p className="font-display text-3xl font-bold">$428,500 MXN</p>
          <p className="text-sm opacity-90">Basado en cotizaciones en negociación</p>
        </div>
      </div>
    </div>
  );
}

function Features() {
  const items = [
    { icon: MessageCircle, title: 'WhatsApp multi-número', text: 'Conecta todos tus números por QR. Un inbox, sub-hilos por cotización, sin chats mezclados.' },
    { icon: Kanban, title: 'Pipeline Kanban visual', text: 'De nueva consulta a cerrada en un tablero que entiende tu equipo. Con alertas de inactividad.' },
    { icon: Calculator, title: 'Motor de precios propio', text: 'Tus fórmulas, tus márgenes, tus comisiones por canal. Nada hardcodeado. Configurable en segundos.' },
    { icon: FileText, title: 'PDF profesional', text: 'Cotización con tu branding, itinerario y desglose. Lista para enviar desde el mismo chat.' },
    { icon: Sparkles, title: 'IA operativa', text: 'Resúmenes automáticos del chat, detección de oportunidades y campos faltantes. Próximamente.' },
    { icon: Smartphone, title: 'PWA instalable', text: 'Úsala como app nativa en Android e iOS. Offline en lo esencial. Sin pasar por stores.' },
  ];
  return (
    <section id="features" className="py-20 md:py-28">
      <div className="max-w-7xl mx-auto px-4 md:px-8">
        <div className="max-w-2xl">
          <p className="pill bg-mint-100 text-emerald-800" data-testid="features-pill">Producto</p>
          <h2 className="font-display text-3xl md:text-5xl font-semibold text-ink-900 mt-4 tracking-tight">
            Todo lo que tu equipo <span className="text-brand-500">necesita antes</span> de la venta.
          </h2>
          <p className="text-ink-500 mt-4 text-lg">
            Fareharbor y Bokun resuelven la post-venta. Routiq cubre el hueco: desde el primer mensaje hasta el cierre.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-10">
          {items.map(({ icon: Icon, title, text }, i) => (
            <div key={title} className="card-surface p-6 animate-fade-up" style={{ animationDelay: `${i * 0.05}s` }}>
              <div className="w-11 h-11 rounded-xl bg-brand-50 text-brand-500 flex items-center justify-center mb-4">
                <Icon className="w-5 h-5" />
              </div>
              <h3 className="font-display font-semibold text-lg text-ink-900">{title}</h3>
              <p className="text-ink-500 text-sm mt-2 leading-relaxed">{text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    { n: '01', title: 'Conecta WhatsApp', text: 'Escanea el QR una vez y deja que Routiq reciba todos tus chats.' },
    { n: '02', title: 'Arma tu catálogo', text: 'Carga paquetes, hoteles, ocupaciones y tus fórmulas de precios.' },
    { n: '03', title: 'Cotiza en 2 minutos', text: 'Constructor guiado. PDF listo con el branding de tu empresa.' },
    { n: '04', title: 'Da seguimiento', text: 'Kanban con alertas si una cotización lleva demasiado sin movimiento.' },
  ];
  return (
    <section id="how" className="py-20 md:py-28 bg-white border-y border-ink-100">
      <div className="max-w-7xl mx-auto px-4 md:px-8 grid md:grid-cols-12 gap-10 items-start">
        <div className="md:col-span-5">
          <p className="pill bg-brand-50 text-brand-500">Cómo funciona</p>
          <h2 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 mt-4 tracking-tight">
            Del caos de WhatsApp a un flujo que tu equipo sigue.
          </h2>
          <p className="text-ink-500 mt-4 leading-relaxed">
            Arranca en un día. Sin romper lo que ya funciona en Fareharbor ni Bokun. Compatible con Meta API
            oficial cuando tu empresa esté lista.
          </p>
          <img src={FEATURE_IMG} alt="Equipo de ventas" className="rounded-2xl mt-8 hidden md:block shadow-lg" />
        </div>
        <ol className="md:col-span-7 space-y-4">
          {steps.map(({ n, title, text }, i) => (
            <li key={n} className="flex gap-5 p-6 rounded-2xl border border-ink-100 bg-cream hover:border-brand-200 hover:bg-white transition-all animate-fade-up" style={{ animationDelay: `${i * 0.06}s` }}>
              <span className="font-display text-3xl font-bold text-brand-500 w-14 shrink-0">{n}</span>
              <div>
                <h3 className="font-display font-semibold text-lg text-ink-900">{title}</h3>
                <p className="text-ink-500 mt-1 leading-relaxed">{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Pricing() {
  const tiers = [
    { name: 'Starter', price: '$890', perks: ['1 número WhatsApp', 'Hasta 3 ejecutivos', 'Cotizaciones ilimitadas', 'PDF con branding'] },
    { name: 'Pro', price: '$1,890', highlight: true, perks: ['Hasta 5 números', 'Hasta 15 ejecutivos', 'IA operativa', 'Kanban + alertas', 'Motor de precios avanzado'] },
    { name: 'Enterprise', price: 'A medida', perks: ['Números ilimitados', 'Meta API oficial', 'SLA dedicado', 'Onboarding + capacitación'] },
  ];
  return (
    <section id="pricing" className="py-20 md:py-28">
      <div className="max-w-7xl mx-auto px-4 md:px-8">
        <div className="text-center max-w-2xl mx-auto">
          <p className="pill bg-peach-100 text-amber-800">Planes</p>
          <h2 className="font-display text-3xl md:text-5xl font-semibold text-ink-900 mt-4 tracking-tight">
            Precios simples que crecen con tu operación.
          </h2>
          <p className="text-ink-500 mt-4">MXN al mes por empresa. Sin costo por mensaje. Sin costo por usuario extra hasta el límite del plan.</p>
        </div>
        <div className="grid md:grid-cols-3 gap-5 mt-10">
          {tiers.map((t) => (
            <div key={t.name}
              className={`rounded-2xl p-7 transition-all ${t.highlight ? 'bg-brand-500 text-white shadow-xl scale-[1.02]' : 'bg-white border border-ink-100'}`}
              data-testid={`pricing-tier-${t.name.toLowerCase()}`}>
              <p className={`text-xs uppercase font-bold tracking-widest ${t.highlight ? 'text-brand-50' : 'text-ink-400'}`}>{t.name}</p>
              <p className={`font-display text-4xl font-bold mt-2 ${t.highlight ? 'text-white' : 'text-ink-900'}`}>{t.price}<span className="text-base font-normal opacity-70"> /mes</span></p>
              <ul className={`mt-5 space-y-2 text-sm ${t.highlight ? 'text-white/90' : 'text-ink-700'}`}>
                {t.perks.map((p) => (
                  <li key={p} className="flex items-start gap-2"><Check className={`w-4 h-4 mt-0.5 ${t.highlight ? 'text-mint-100' : 'text-brand-500'}`} />{p}</li>
                ))}
              </ul>
              <Link to="/login" className={`mt-6 w-full justify-center ${t.highlight ? 'btn-secondary' : 'btn-primary'}`} data-testid={`pricing-cta-${t.name.toLowerCase()}`}>
                Comenzar
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section id="demo" className="relative py-24 md:py-32 bg-brand-500 text-white overflow-hidden">
      <div className="absolute inset-0 grain opacity-20" />
      <div className="relative max-w-5xl mx-auto px-4 md:px-8 text-center space-y-6">
        <h2 className="font-display text-4xl md:text-6xl font-bold tracking-tight">Digitaliza tu cotización hoy.</h2>
        <p className="text-lg text-brand-50 max-w-2xl mx-auto">Reserva una demo de 20 min o entra directo con tus credenciales de prueba.</p>
        <div className="flex flex-wrap justify-center gap-3 pt-2">
          <Link to="/login" className="btn-secondary" data-testid="final-cta-login">Entrar al sistema <ArrowRight className="w-4 h-4" /></Link>
          <a href="mailto:hola@routiq.mx" className="btn-ghost !text-white hover:!bg-white/10" data-testid="final-cta-email">Escribir a ventas</a>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="bg-ink-900 text-white py-10">
      <div className="max-w-7xl mx-auto px-4 md:px-8 flex flex-col md:flex-row items-center justify-between gap-4">
        <Logo size={26} white />
        <p className="text-sm text-white/60">© 2026 Routiq. Hecho para tour operadores. GDL 🇲🇽</p>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen bg-cream" data-testid="landing-page">
      <NavBar />
      <Hero />
      <Features />
      <HowItWorks />
      <Pricing />
      <FinalCta />
      <Footer />
    </div>
  );
}
