import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { drawPhoneScreen, type PhoneScreenState } from './drawPhoneScreen'

interface ExplodedPhoneCanvasProps {
  progress: number
}

export function ExplodedPhoneCanvas({ progress }: ExplodedPhoneCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const progressRef = useRef(progress)
  progressRef.current = progress

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    // Setup offscreen canvas for dynamic screen texture
    const screenCanvas = document.createElement('canvas')
    screenCanvas.width = 512
    screenCanvas.height = 1024
    const screenCtx = screenCanvas.getContext('2d')
    if (!screenCtx) return

    const screenTexture = new THREE.CanvasTexture(screenCanvas)
    screenTexture.anisotropy = 4

    // Three.js Scene Setup
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(
      42,
      container.clientWidth / container.clientHeight,
      0.1,
      100
    )
    camera.position.set(0, 0, 7.8)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setSize(container.clientWidth, container.clientHeight)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.2
    container.appendChild(renderer.domElement)

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7)
    scene.add(ambientLight)

    const goldKeyLight = new THREE.DirectionalLight(0xc9a96e, 2.8)
    goldKeyLight.position.set(4, 5, 6)
    scene.add(goldKeyLight)

    const dynamicRimLight = new THREE.DirectionalLight(0x4ade80, 2.0)
    dynamicRimLight.position.set(-4, -2, -3)
    scene.add(dynamicRimLight)

    // Root Group for phone and exploded layers
    const phoneGroup = new THREE.Group()
    scene.add(phoneGroup)

    // 1. Titanium Chassis Frame
    const chassisGeo = new THREE.BoxGeometry(2.5, 5.0, 0.18)
    const chassisMat = new THREE.MeshStandardMaterial({
      color: 0x141419,
      metalness: 0.9,
      roughness: 0.25,
    })
    const chassisMesh = new THREE.Mesh(chassisGeo, chassisMat)
    phoneGroup.add(chassisMesh)

    // 2. Beveled Gold Trim Outline
    const frameEdges = new THREE.EdgesGeometry(chassisGeo)
    const frameLineMat = new THREE.LineBasicMaterial({
      color: 0xc9a96e,
      transparent: true,
      opacity: 0.35,
    })
    const frameOutline = new THREE.LineSegments(frameEdges, frameLineMat)
    chassisMesh.add(frameOutline)

    // 3. Back Plate
    const backGeo = new THREE.BoxGeometry(2.44, 4.94, 0.04)
    const backMat = new THREE.MeshStandardMaterial({
      color: 0x0c0c0f,
      metalness: 0.8,
      roughness: 0.4,
    })
    const backMesh = new THREE.Mesh(backGeo, backMat)
    backMesh.position.z = -0.11
    phoneGroup.add(backMesh)

    // 4. Front Screen Glass with Canvas Texture
    const screenGeo = new THREE.PlaneGeometry(2.36, 4.86)
    const screenMat = new THREE.MeshBasicMaterial({
      map: screenTexture,
      transparent: true,
    })
    const screenMesh = new THREE.Mesh(screenGeo, screenMat)
    screenMesh.position.z = 0.1
    phoneGroup.add(screenMesh)

    // 5. Four Holographic Exploded Inspection Plates
    // Plate 1: XLS-R + AASIST Spectral Waveform
    const waveGeo = new THREE.PlaneGeometry(2.1, 1.0, 16, 8)
    const waveMat = new THREE.MeshBasicMaterial({
      color: 0x4ade80,
      wireframe: true,
      transparent: true,
      opacity: 0.7,
    })
    const wavePlate = new THREE.Mesh(waveGeo, waveMat)
    wavePlate.position.set(0, 1.4, 0)
    phoneGroup.add(wavePlate)

    // Plate 2: ECAPA-TDNN Speaker Identity Vector Sphere
    const sphereGeo = new THREE.IcosahedronGeometry(0.55, 2)
    const sphereMat = new THREE.MeshBasicMaterial({
      color: 0xc9a96e,
      wireframe: true,
      transparent: true,
      opacity: 0.75,
    })
    const vectorPlate = new THREE.Mesh(sphereGeo, sphereMat)
    vectorPlate.position.set(0, 0.4, 0)
    phoneGroup.add(vectorPlate)

    // Plate 3: openSMILE Prosody & Pitch Ribbon
    const curvePoints = []
    for (let i = 0; i <= 24; i++) {
      const x = -1.0 + (i / 24) * 2.0
      const y = Math.sin(i * 0.8) * 0.25
      curvePoints.push(new THREE.Vector3(x, y, 0))
    }
    const prosodyCurve = new THREE.CatmullRomCurve3(curvePoints)
    const prosodyGeo = new THREE.TubeGeometry(prosodyCurve, 32, 0.02, 6, false)
    const prosodyMat = new THREE.MeshBasicMaterial({
      color: 0xfbbf24,
      transparent: true,
      opacity: 0.8,
    })
    const prosodyPlate = new THREE.Mesh(prosodyGeo, prosodyMat)
    prosodyPlate.position.set(0, -0.6, 0)
    phoneGroup.add(prosodyPlate)

    // Plate 4: STT + LLM Scam Intent Lattice
    const latticeGeo = new THREE.PlaneGeometry(2.1, 0.8, 8, 4)
    const latticeMat = new THREE.MeshBasicMaterial({
      color: 0xf87171,
      wireframe: true,
      transparent: true,
      opacity: 0.65,
    })
    const latticePlate = new THREE.Mesh(latticeGeo, latticeMat)
    latticePlate.position.set(0, -1.6, 0)
    phoneGroup.add(latticePlate)

    const plates = [wavePlate, vectorPlate, prosodyPlate, latticePlate]

    // Animation & Smooth Lerp variables
    let currentProgress = 0
    let callDuration = 14.0
    let isVisible = true
    let animId = 0

    // IntersectionObserver to pause loop when out of viewport
    const observer = new IntersectionObserver(
      ([entry]) => {
        isVisible = entry.isIntersecting
      },
      { threshold: 0.05 }
    )
    observer.observe(container)

    // Resize handler
    const handleResize = () => {
      if (!container) return
      const w = container.clientWidth
      const h = container.clientHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', handleResize)

    // Main Render Loop
    const render = () => {
      animId = requestAnimationFrame(render)
      if (!isVisible) return

      callDuration += 0.016
      const targetP = progressRef.current
      currentProgress += (targetP - currentProgress) * 0.08

      // Determine explosion factor (peaks during Stage 04: p = 0.25 -> 0.65)
      let explosion = 0
      if (currentProgress >= 0.15 && currentProgress < 0.7) {
        // Curve smoothly rises and falls
        const t = (currentProgress - 0.15) / 0.55
        explosion = Math.sin(t * Math.PI)
      }

      // 1. Transform Phone Body & Camera
      if (currentProgress < 0.2) {
        // Initial resting isometric position
        phoneGroup.rotation.y = 0.35 - currentProgress * 0.5
        phoneGroup.rotation.x = 0.12
        phoneGroup.rotation.z = -0.05
      } else if (currentProgress < 0.75) {
        // Exploded inspection angle: rotated to show sandwich depth
        phoneGroup.rotation.y = 0.55 + explosion * 0.2
        phoneGroup.rotation.x = 0.18 + explosion * 0.1
        phoneGroup.rotation.z = -0.08
      } else {
        // Final stage: Reassembled phone faces forward to highlight the in-call warning overlay
        const t = (currentProgress - 0.75) / 0.25
        phoneGroup.rotation.y = THREE.MathUtils.lerp(0.55, 0.0, t)
        phoneGroup.rotation.x = THREE.MathUtils.lerp(0.18, 0.0, t)
        phoneGroup.rotation.z = THREE.MathUtils.lerp(-0.08, 0.0, t)
      }

      // 2. Explode individual layers along Z
      screenMesh.position.z = 0.1 + explosion * 1.6
      backMesh.position.z = -0.11 - explosion * 1.2

      // Animate inspection plates
      plates.forEach((plate, i) => {
        const offsetZ = 0.3 + (i + 1) * 0.28
        plate.position.z = explosion * offsetZ
        plate.visible = explosion > 0.05
        // subtle idle rotation
        plate.rotation.z = Math.sin(callDuration * 2 + i) * 0.03
      })
      vectorPlate.rotation.y += 0.015

      // 3. Update lighting color based on risk escalation
      if (currentProgress > 0.7) {
        dynamicRimLight.color.setHex(0xf87171) // Critical red glow
        goldKeyLight.intensity = 3.2
      } else {
        dynamicRimLight.color.setHex(0x4ade80) // Normal green assurance
        goldKeyLight.intensity = 2.8
      }

      // 4. Redraw 2D Canvas Screen Texture
      const screenState: PhoneScreenState = {
        progress: currentProgress,
        callDuration,
        callerName: currentProgress > 0.7 ? 'Managing Director (Alleged)' : 'Ramesh Kumar (Regional)',
        callerNumber: '+91 98201 44820',
      }
      drawPhoneScreen(screenCtx, screenCanvas.width, screenCanvas.height, screenState)
      screenTexture.needsUpdate = true

      renderer.render(scene, camera)
    }

    render()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', handleResize)
      observer.disconnect()
      renderer.dispose()
      screenTexture.dispose()
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full min-h-[460px] md:min-h-[580px]"
      aria-label="Interactive 3D exploded view of SatyaCheck live call architecture"
    />
  )
}
