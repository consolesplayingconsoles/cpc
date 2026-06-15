import imgWii      from '../assets/avatars/wii.png'
import imgDc       from '../assets/avatars/dc.png'
import imgVmu      from '../assets/avatars/vmu.png'
import imgPs3      from '../assets/avatars/ps3.png'
import imgGba      from '../assets/avatars/gba.png'
import imgWs       from '../assets/avatars/ws.png'
import imgBatocera from '../assets/avatars/batocera.png'
import imgDreame   from '../assets/avatars/dreame.png'
import imgHost     from '../assets/avatars/host.png'
import imgClaude   from '../assets/avatars/claude.svg'
import imgBird     from '../assets/avatars/birdbuddy.png'
import imgPi       from '../assets/avatars/pi.svg'
import imgCloud    from '../assets/avatars/cloud.svg'
import imgCloudStorage from '../assets/avatars/cloud-storage.svg'
import imgSaturn    from '../assets/avatars/saturn.png'
import imgMegadrive from '../assets/avatars/megadrive.png'
import imgSubstack  from '../assets/avatars/substack.svg'
import imgGateway   from '../assets/avatars/gateway.svg'

export const ICONS: Record<string, string> = {
  wii:       imgWii,
  dc:        imgDc,
  vmu:       imgVmu,
  ps3:       imgPs3,
  gba:       imgGba,
  ws:        imgWs,
  batocera:  imgBatocera,
  dreame:    imgDreame,
  pluto:     imgHost,
  saturn:    imgSaturn,
  megadrive: imgMegadrive,
  claude:        imgClaude,
  birdbuddy:     imgBird,
  pi:            imgPi,
  cloud:         imgCloud,
  dropbox:       imgCloudStorage,   // operator-named storage node; generic brandless glyph
  dreamehome:    imgDreame,    // the vacuum's cloud — reuses the Dreame mark
  substack:      imgSubstack,
  gateway:       imgGateway,   // its own signal/router mark — so it doesn't fall back to the guest icon
}
