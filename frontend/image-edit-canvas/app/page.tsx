'use client'

import dynamic from 'next/dynamic'
import { useEffect, useRef, useState, useId } from 'react'
import { useRouter } from 'next/navigation'
import { createSession, listImages, uploadImage } from '../lib/api'

const InfiniteCanvas = dynamic(() => import('../components/InfiniteCanvas'), {
  ssr: false,
})

export default function Page() {
  const router = useRouter()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [images, setImages] = useState<{ key: string; url: string; x: number; y: number }[]>([])
  const [busy, setBusy] = useState(false)
  const [scale, setScale] = useState(1)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const canvasApi = useRef<{ zoomIn: () => void; zoomOut: () => void; reset: () => void } | null>(null)
  const inputId = useId()

  useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const sp = new URLSearchParams(window.location.search)
        let sid = sp.get('session_id')
        if (!sid) {
          sid = await createSession()
          if (!mounted) return
          sp.set('session_id', sid)
          router.replace(`?${sp.toString()}`, { scroll: false })
        }
        setSessionId(sid)
        const res = await listImages(sid)
        if (!mounted) return
        setImages(res)
      } catch (e) {
        console.error('Failed to init session', e)
      }
    })()
    return () => {
      mounted = false
    }
  }, [router])

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!sessionId) return
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    try {
      const item = await uploadImage(sessionId, file)
      setImages((prev) => [...prev, item])
    } catch (err) {
      console.error('Upload failed', err)
    } finally {
      setBusy(false)
      e.target.value = ''
    }
  }

  return (
    <>
      {/* Hidden file input */}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        onChange={onFileChange}
        disabled={!sessionId || busy}
        id={inputId}
        style={{
          position: 'absolute',
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: 'hidden',
          clip: 'rect(0, 0, 0, 0)',
          whiteSpace: 'nowrap',
          border: 0,
        } as React.CSSProperties}
      />

      {/* Left toolbar with + button */}
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: 12,
          transform: 'translateY(-50%)',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          zIndex: 10,
        }}
      >
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
            background: '#fff',
            border: '1px solid #e5e5e5',
            borderRadius: 18,
            padding: 8,
            boxShadow: '0 2px 10px rgba(0,0,0,0.06)'
          }}
        >
          <label
            aria-label="Upload image"
            htmlFor={inputId}
            style={{
              display: 'grid',
              placeItems: 'center',
              width: 48,
              height: 48,
              borderRadius: 24,
              fontSize: 22,
              background: (!sessionId || busy) ? '#999' : '#111',
              color: '#fff',
              cursor: (!sessionId || busy) ? 'not-allowed' : 'pointer',
              userSelect: 'none',
            }}
            title={!sessionId ? 'Preparing session...' : (busy ? 'Uploading...' : 'Upload image')}
          >
            +
          </label>
        </div>
      </div>

      {/* Zoom indicator */}
      <div
        style={{
          position: 'fixed',
          left: 12,
          bottom: 12,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 8px',
          background: '#fff',
          border: '1px solid #e5e5e5',
          borderRadius: 12,
          boxShadow: '0 2px 10px rgba(0,0,0,0.06)',
          zIndex: 10,
        }}
      >
        <button aria-label="Zoom in" onClick={() => canvasApi.current?.zoomIn()} style={{ width: 28, height: 28, borderRadius: 6 }}>+</button>
        <span style={{ minWidth: 44, textAlign: 'center', fontSize: 12 }}>{Math.round(scale * 100)}%</span>
        <button aria-label="Zoom out" onClick={() => canvasApi.current?.zoomOut()} style={{ width: 28, height: 28, borderRadius: 6 }}>−</button>
      </div>

      <InfiniteCanvas
        images={images}
        sessionId={sessionId}
        onScaleChange={setScale}
        apiRef={(api) => { canvasApi.current = api }}
      />
    </>
  )
}
