import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/register", "/jobs"];
const PUBLIC_PREFIXES = ["/invites/", "/_next/", "/api/", "/favicon"];

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.includes(pathname)) return true;
  return PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isViewerOnlyPath(pathname: string): boolean {
  return pathname.startsWith("/workspace");
}

function rewriteUrl(pathname: string, request: NextRequest, params?: Record<string, string>): URL {
  const url = request.nextUrl.clone();
  url.pathname = pathname;
  url.search = "";
  Object.entries(params ?? {}).forEach(([key, value]) => url.searchParams.set(key, value));
  return url;
}

function rewriteTo(pathname: string, request: NextRequest, params?: Record<string, string>): NextResponse {
  return NextResponse.rewrite(rewriteUrl(pathname, request, params));
}

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  // Skip public paths
  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  // Check session cookie for authentication
  const sessionCookie = request.cookies.get("cognitrix_session");
  const hasSession = Boolean(sessionCookie?.value);

  if (!hasSession) {
    return rewriteTo("/login", request, { next: pathname });
  }

  // Viewer mode: redirect workspace paths to portal
  const appMode = request.cookies.get("cognitrix_app_mode")?.value ?? "designer";
  if (appMode === "viewer" && isViewerOnlyPath(pathname)) {
    return rewriteTo("/portal", request);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon\\.ico).*)",
  ],
};
