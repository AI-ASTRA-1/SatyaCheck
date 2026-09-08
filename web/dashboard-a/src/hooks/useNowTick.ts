import { useEffect, useState } from 'react'

/** Re-renders on an interval so elapsed-time captions ("Ns ago") stay live. */
export function useNowTick(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])

  return now
}
