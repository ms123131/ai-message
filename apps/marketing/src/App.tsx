import { Header } from "./components/Header";
import { Hero } from "./sections/Hero";
import { Problems } from "./sections/Problems";
import { HowItWorks } from "./sections/HowItWorks";
import { Screenshots } from "./sections/Screenshots";
import { Features } from "./sections/Features";
import { Pricing } from "./sections/Pricing";
import { FAQ } from "./sections/FAQ";
import { FinalCTA } from "./sections/FinalCTA";
import { Footer } from "./sections/Footer";

export default function App() {
  return (
    <div className="min-h-screen bg-white text-slate-900 antialiased">
      <Header />
      <main>
        <Hero />
        <Problems />
        <HowItWorks />
        <Screenshots />
        <Features />
        <Pricing />
        <FAQ />
        <FinalCTA />
      </main>
      <Footer />
    </div>
  );
}
