/// <reference types="vite/client" />
interface ImportMetaEnv {
  /** Reown project ID (dashboard.reown.com). Optional: without it the app uses
   *  the browser's injected wallet only. */
  readonly VITE_REOWN_PROJECT_ID?: string;
}
declare module "*.py?raw" {
  const src: string;
  export default src;
}
declare module "*.md?raw" {
  const src: string;
  export default src;
}
