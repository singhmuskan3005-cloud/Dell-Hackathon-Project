import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({
    request,
  })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => request.cookies.set(name, value))
          supabaseResponse = NextResponse.next({
            request,
          })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  // refreshing the auth token
  const {
    data: { user },
  } = await supabase.auth.getUser()

  const isAuthRoute = request.nextUrl.pathname.startsWith('/auth')
  const isParticipantRoute = request.nextUrl.pathname.startsWith('/participant') || request.nextUrl.pathname.startsWith('/onboarding')
  const isOrganizerRoute = request.nextUrl.pathname.startsWith('/organizer')

  // Redirect logic
  if (!user && (isParticipantRoute || isOrganizerRoute)) {
    const url = request.nextUrl.clone()
    url.pathname = isOrganizerRoute ? '/auth/organizer' : '/auth/participant'
    return NextResponse.redirect(url)
  }

  // Optional: Redirect authenticated users away from auth pages
  if (user && isAuthRoute) {
    if (request.nextUrl.pathname.startsWith('/auth/reviewer')) {
      return supabaseResponse;
    }

    const url = request.nextUrl.clone()
    const role = user.user_metadata?.role;
    
    if (role === 'organizer') {
      url.pathname = '/organizer/dashboard'
    } else {
      url.pathname = '/participant/dashboard'
    }
    
    return NextResponse.redirect(url)
  }

  return supabaseResponse
}
