import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Serveur autonome pour l'image Docker : n'emporte que les dépendances
  // réellement utilisées, au lieu de tout node_modules.
  output: 'standalone',
  poweredByHeader: false,
};

export default nextConfig;
