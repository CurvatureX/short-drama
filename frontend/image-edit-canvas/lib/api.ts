const BASE = process.env.NEXT_PUBLIC_CANVAS_API_URL || 'http://localhost:9000'
const ORCH_BASE = process.env.NEXT_PUBLIC_ORCH_URL || 'http://localhost:8080'

export async function createSession(): Promise<string> {
  const res = await fetch(`${BASE}/session`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to create session')
  const data = await res.json()
  return data.session_id as string
}

export async function uploadImage(sessionId: string, file: File): Promise<{ key: string; url: string; x: number; y: number }> {
  const form = new FormData()
  form.append('session_id', sessionId)
  form.append('file', file)
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Upload failed')
  return res.json()
}

export async function listImages(sessionId: string): Promise<{ key: string; url: string; x: number; y: number }[]> {
  const res = await fetch(`${BASE}/images?session_id=${encodeURIComponent(sessionId)}`)
  if (!res.ok) throw new Error('List images failed')
  const data = await res.json()
  return (data.items || []) as { key: string; url: string; x: number; y: number }[]
}

export async function addImageToSession(sessionId: string, s3Key: string, x: number = 0, y: number = 0): Promise<{ key: string; url: string; x: number; y: number }> {
  const res = await fetch(`${BASE}/add-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, s3_key: s3Key, x, y }),
  })
  if (!res.ok) throw new Error('Add image to session failed')
  return res.json()
}

export async function updateImagePosition(sessionId: string, s3Key: string, x: number, y: number): Promise<void> {
  const res = await fetch(`${BASE}/update-position`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, s3_key: s3Key, x, y }),
  })
  if (!res.ok) throw new Error('Update position failed')
}

export async function deleteImage(sessionId: string, s3Key: string): Promise<void> {
  const res = await fetch(`${BASE}/delete-image`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, s3_key: s3Key }),
  })
  if (!res.ok) throw new Error('Delete image failed')
}

// ==================== Orchestrator API Types ====================

export type JobStatus = 'pending' | 'completed' | 'failed'

export interface JobResponse {
  job_id: string
  status: JobStatus
  result_url?: string
  error?: string
}

// ==================== Orchestrator API Functions ====================

/**
 * Submit a Qwen image edit job to the orchestrator
 * Returns immediately with job_id, client should poll for completion
 */
export async function submitQwenEdit(imageUrl: string, prompt: string): Promise<JobResponse> {
  const res = await fetch(`${ORCH_BASE}/api/v1/qwen-image-edit/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_url: imageUrl, prompt, steps: 4 }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Qwen edit failed: ${res.status} ${text}`)
  }
  return res.json()
}

/**
 * Submit a camera angle transformation job to the orchestrator
 * Returns immediately with job_id, client should poll for completion
 */
export async function submitCameraAngle(
  imageUrl: string,
  params: {
    vertical: number // -2, -1, 0, 1, 2
    horizontal: number // -2, -1, 0, 1, 2
    zoom: number // -1, 0, 1
  }
): Promise<JobResponse> {
  const res = await fetch(`${ORCH_BASE}/api/v1/camera-angle/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      image_url: imageUrl,
      vertical: params.vertical,
      horizontal: params.horizontal,
      zoom: params.zoom,
      steps: 8,
    }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Camera angle failed: ${res.status} ${text}`)
  }
  return res.json()
}

/**
 * Get the status of a job by job_id
 */
export async function getJobStatus(jobId: string): Promise<JobResponse> {
  const res = await fetch(`${ORCH_BASE}/api/v1/jobs/${jobId}`)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Get job status failed: ${res.status} ${text}`)
  }
  return res.json()
}

/**
 * Poll a job until it completes or fails
 * Polls every 1 second, returns when job is completed or failed
 *
 * Includes retry logic: if job not found (404), retries up to 3 times
 * before throwing an error. This handles eventual consistency issues.
 *
 * @param jobId - The job ID to poll
 * @param onUpdate - Optional callback called on each status update
 * @returns The final job response when completed or failed
 */
export async function pollJobStatus(
  jobId: string,
  onUpdate?: (status: JobResponse) => void
): Promise<JobResponse> {
  let notFoundRetries = 0
  const maxNotFoundRetries = 3

  while (true) {
    try {
      const status = await getJobStatus(jobId)

      // Reset retry counter on successful fetch
      notFoundRetries = 0

      onUpdate?.(status)

      if (status.status === 'completed' || status.status === 'failed') {
        return status
      }

      // Wait 1 second before next poll
      await new Promise(resolve => setTimeout(resolve, 1000))
    } catch (error) {
      // Handle "Job not found" (404) errors with retry logic
      if (error instanceof Error && error.message.includes('404')) {
        notFoundRetries++
        console.warn(`Job ${jobId} not found (attempt ${notFoundRetries}/${maxNotFoundRetries}), retrying...`)

        if (notFoundRetries >= maxNotFoundRetries) {
          // After max retries, throw the error
          throw new Error(`Job ${jobId} not found after ${maxNotFoundRetries} retries`)
        }

        // Wait 2 seconds before retrying on 404
        await new Promise(resolve => setTimeout(resolve, 2000))
      } else {
        // For other errors, throw immediately
        throw error
      }
    }
  }
}

// ==================== Face Mask & Face Swap (CPU Tasks) ====================

/**
 * Submit a face mask task
 * Returns job_id in the same format as other tasks
 */
export async function submitFaceMask(
  imageUrl: string,
  options?: {
    facePositionPrompt?: string
    faceIndex?: number
  }
): Promise<JobResponse> {
  const res = await fetch(`${ORCH_BASE}/api/v1/face-mask/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      image_url: imageUrl,
      face_position_prompt: options?.facePositionPrompt,
      face_index: options?.faceIndex || 0,
    }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Face mask failed: ${res.status} ${text}`)
  }
  return res.json()
}

/**
 * Submit a face swap task
 *
 * NOTE: sourceImageUrl should be a pre-masked image.
 * This API does NOT perform face detection or masking.
 * Use submitFaceMask() first to generate the masked image.
 *
 * Returns job_id in the same format as other tasks
 */
export async function submitFaceSwap(
  sourceImageUrl: string,  // Should be a pre-masked image
  targetFaceUrl: string,
  options?: {
    model?: string
    facePositionPrompt?: string
    expressionPrompt?: string
    faceIndex?: number
  }
): Promise<JobResponse> {
  const res = await fetch(`${ORCH_BASE}/api/v1/full-face-swap/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_image_url: sourceImageUrl,
      target_face_url: targetFaceUrl,
      model: options?.model || 'seedream',
      face_position_prompt: options?.facePositionPrompt,
      expression_prompt: options?.expressionPrompt,
      face_index: options?.faceIndex || 0,
      size: 'auto',
    }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Face swap failed: ${res.status} ${text}`)
  }
  const data = await res.json()
  // Return the response directly - API already returns job_id
  return {
    job_id: data.job_id,
    status: data.status,
    result_url: data.result_url,
    error: data.error,
  }
}

/**
 * Poll a face swap task - same as pollJobStatus since both use unified orchestrator
 */
export const pollFaceSwapStatus = pollJobStatus
