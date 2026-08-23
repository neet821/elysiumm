import * as THREE from 'three'

export const SCENERY_URLS = Object.freeze({
  nature: '/scenery/nature-window.webp',
  city: '/scenery/city.svg',
  cloudy: '/scenery/cloudy.svg',
  night: '/scenery/night.svg',
})

export const DEFAULT_SCENERY = 'nature'

export function resolveSceneryUrl(scenery) {
  return SCENERY_URLS[scenery] ?? SCENERY_URLS[DEFAULT_SCENERY]
}

function createGeneratedFallbackTexture() {
  const data = new Uint8Array([
    133, 183, 211, 255,
    216, 236, 224, 255,
    98, 139, 110, 255,
    172, 202, 162, 255,
  ])
  const texture = new THREE.DataTexture(data, 2, 2, THREE.RGBAFormat)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  return texture
}

function prepareTexture(texture) {
  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter
  texture.magFilter = THREE.LinearFilter
  return texture
}

export async function loadSceneryTexture(scenery, loader = new THREE.TextureLoader()) {
  const requestedScenery = Object.hasOwn(SCENERY_URLS, scenery) ? scenery : DEFAULT_SCENERY
  const requestedUrl = resolveSceneryUrl(requestedScenery)

  try {
    return {
      texture: prepareTexture(await loader.loadAsync(requestedUrl)),
      scenery: requestedScenery,
    }
  } catch {
    if (requestedUrl !== SCENERY_URLS[DEFAULT_SCENERY]) {
      try {
        return {
          texture: prepareTexture(await loader.loadAsync(SCENERY_URLS[DEFAULT_SCENERY])),
          scenery: DEFAULT_SCENERY,
        }
      } catch {
        return { texture: createGeneratedFallbackTexture(), scenery: DEFAULT_SCENERY }
      }
    }
    return { texture: createGeneratedFallbackTexture(), scenery: DEFAULT_SCENERY }
  }
}
