/** Release tag of the web image, set at build time (``sha-1a2b3c4``); ``dev`` locally. */
export const WEB_VERSION: string = import.meta.env.VITE_APP_VERSION || 'dev'
