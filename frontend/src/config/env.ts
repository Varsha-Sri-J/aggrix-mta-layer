/**
 * AGGRIX MTA Layer — Frontend Environment Configuration
 */

export interface AppEnvConfig {
  apiBaseUrl: string
  appEnv: string
  isDev: boolean
}

export const env: AppEnvConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? (typeof window !== 'undefined' ? '' : 'http://localhost:8000'),
  appEnv: import.meta.env.VITE_APP_ENV || 'development',
  isDev: import.meta.env.DEV,
}

