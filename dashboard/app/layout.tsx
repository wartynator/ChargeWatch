import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
const inter = Inter({ subsets: ['latin', 'latin-ext'], variable: '--font-inter' });
export const metadata: Metadata = { title: 'ChargeWatch | Vyťaženosť staníc', description: 'História dostupnosti nabíjacích konektorov na stanici OC Optima Košice.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="sk"><body className={inter.variable}>{children}</body></html>; }
