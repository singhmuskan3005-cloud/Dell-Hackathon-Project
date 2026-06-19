'use server'

import { createClient } from '@/utils/supabase/server'
import { getDecisionForRegistration } from '@/components/registrations/registrationIntelligenceModel'

// Note: In a real environment, you'd perform FaceScan/RapidFuzz calls here.
// For now, we simulate the "intelligence" using the frontend model logic.
export async function submitRegistration(payload: any) {
  const supabase = await createClient()

  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    return { success: false, error: 'Unauthorized' }
  }

  // 1. Generate Intelligence Decision
  // We mock exactSignals and similarity based on the PRD for this participant
  const intelligencePayload = {
    ...payload,
    exactSignals: {
      email: false,
      phone: false,
      github: false,
    },
    similarity: {
      name: Math.random() * 0.3, // Mock low similarity
      college: Math.random() * 0.3,
    },
    deviceMatch: false,
    ipSubnetMatch: false,
    faceScan: {
      status: 'verified',
      score: 0.95,
      consented: true,
      dataDeletedAt: new Date().toISOString(),
    }
  }

  const decision = getDecisionForRegistration(intelligencePayload)
  
  // Compute score for storage
  // Note: we can import computeWeightedScore if we need it
  let score = 0;
  if (decision === 'HARD_DUPLICATE') score = 1.0;
  else if (decision === 'POTENTIAL_DUPLICATE') score = 0.9;
  else if (decision === 'MANUAL_REVIEW') score = 0.75;
  else score = 0.2;

  // 2. Persist to Supabase
  const dbPayload = {
    user_id: user.id,
    name: payload.name,
    email: payload.email,
    college: payload.college,
    github: payload.github,
    skills: payload.skills || [],
    
    decision: decision,
    score: score,
    
    exact_email: false,
    exact_phone: false,
    exact_github: false,
    
    sim_name: intelligencePayload.similarity.name,
    sim_college: intelligencePayload.similarity.college,
    
    device_match: false,
    ip_subnet_match: false,
    
    face_scan_status: intelligencePayload.faceScan.status,
    face_scan_score: intelligencePayload.faceScan.score,
    face_scan_consented: intelligencePayload.faceScan.consented,
    
    recommendation: `Server generated decision: ${decision}`
  }

  const { error } = await supabase.from('registrations').insert(dbPayload)

  if (error) {
    console.error('Registration insertion failed:', error)
    return { success: false, error: error.message }
  }

  return { success: true, decision }
}

export async function fetchRegistrations() {
  const supabase = await createClient()

  // For organizers
  const { data, error } = await supabase
    .from('registrations')
    .select('*')
    .order('created_at', { ascending: false })

  if (error || !data) {
    console.error('Error fetching registrations:', error)
    return []
  }

  // Map flat DB rows to nested RegistrationCase interface
  return data.map((row) => ({
    id: row.id,
    name: row.name,
    email: row.email,
    college: row.college,
    github: row.github,
    submittedAt: new Date(row.submitted_at).toLocaleString(),
    decision: row.decision,
    score: row.score,
    matchedProfile: row.matched_profile || 'No close match',
    matchedProfileNote: row.matched_profile_note || 'No review notes.',
    initials: row.name.split(' ').map((n: string) => n[0]).join('').substring(0, 2).toUpperCase(),
    skills: row.skills || [],
    exactSignals: {
      email: row.exact_email,
      phone: row.exact_phone,
      github: row.exact_github,
    },
    similarity: {
      name: row.sim_name,
      college: row.sim_college,
    },
    deviceMatch: row.device_match,
    ipSubnetMatch: row.ip_subnet_match,
    faceScan: {
      status: row.face_scan_status,
      score: row.face_scan_score,
      consented: row.face_scan_consented,
      dataDeletedAt: row.face_scan_deleted_at,
    },
    recommendation: row.recommendation,
  }))
}
