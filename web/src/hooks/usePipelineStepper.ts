import { useEffect, useRef, useState } from 'react'

const STEP_DURATIONS = [800, 2200, 1200, 1600, 400, 1000, 1100, 2400, 1600]

export function usePipelineStepper(isRunning: boolean): number {
  const [currentStep, setCurrentStep] = useState(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!isRunning) {
      setCurrentStep(0)
      return
    }

    let step = 0

    const advance = () => {
      step++
      setCurrentStep(step)
      if (step < 9) {
        timerRef.current = setTimeout(advance, STEP_DURATIONS[step] ?? 1500)
      }
    }

    timerRef.current = setTimeout(advance, STEP_DURATIONS[0])

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [isRunning])

  return currentStep
}
