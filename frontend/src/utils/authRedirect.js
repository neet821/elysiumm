export const AUTH_REDIRECT_STORAGE_KEY = "blue_album_auth_redirect";

export const shouldBypassAuthRedirect = (pathname = "") => (
  pathname === "/login" || pathname === "/register" || pathname === "/live"
);

export const getLocationTarget = (location = {}) => {
  const pathname = location.pathname || "/";
  const search = location.search || "";
  const hash = location.hash || "";
  return `${pathname}${search}${hash}`;
};

export const getSafeRedirectTarget = (target, fallback = "/") => {
  if (!target || typeof target !== "string") {
    return fallback;
  }

  const trimmed = target.trim();
  if (
    !trimmed.startsWith("/") ||
    trimmed.startsWith("//") ||
    trimmed.startsWith("/\\")
  ) {
    return fallback;
  }

  const pathname = trimmed.split(/[?#]/, 1)[0];
  if (shouldBypassAuthRedirect(pathname)) {
    return fallback;
  }

  return trimmed;
};

export const buildLoginRedirect = (location) => {
  const target = getSafeRedirectTarget(getLocationTarget(location));
  if (target === "/") {
    return "/login";
  }

  return `/login?redirect=${encodeURIComponent(target)}`;
};

export const saveAuthRedirect = (location, storage = globalThis.localStorage) => {
  if (!storage) {
    return;
  }

  const target = getSafeRedirectTarget(getLocationTarget(location));
  if (target !== "/") {
    storage.setItem(AUTH_REDIRECT_STORAGE_KEY, target);
  }
};

export const consumeAuthRedirect = (storage = globalThis.localStorage) => {
  if (!storage) {
    return "/";
  }

  const target = getSafeRedirectTarget(
    storage.getItem(AUTH_REDIRECT_STORAGE_KEY),
  );
  storage.removeItem(AUTH_REDIRECT_STORAGE_KEY);
  return target;
};
