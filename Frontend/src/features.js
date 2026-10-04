// Build-time feature switches (Vite env). Everything defaults to off.
export const FEATURES = {
  // The 90-second recap video is a design mock until video generation exists.
  video: import.meta.env.VITE_FEATURE_VIDEO === "true",
};

// Demo login shortcut for local development only (see Frontend/.env.development). Production
// builds drop it (and the credentials) even if a VITE_DEMO_* variable is set somewhere.
export const DEMO_LOGIN =
  import.meta.env.DEV && import.meta.env.VITE_DEMO_EMAIL && import.meta.env.VITE_DEMO_PASSWORD
    ? { email: import.meta.env.VITE_DEMO_EMAIL, password: import.meta.env.VITE_DEMO_PASSWORD }
    : null;
