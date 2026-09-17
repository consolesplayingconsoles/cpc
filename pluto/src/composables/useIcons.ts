import imgWii      from '../assets/avatars/wii.png'
import imgDc       from '../assets/avatars/dc.png'
import imgVmu      from '../assets/avatars/vmu.png'
import imgPs3      from '../assets/avatars/ps3.png'
import imgGba      from '../assets/avatars/gba.png'
import imgWs       from '../assets/avatars/ws.png'
import imgBatocera from '../assets/avatars/batocera.png'
import imgDreame   from '../assets/avatars/dreame.png'
import imgPlutoC2  from '../assets/avatars/pluto-c2.svg'
import imgPlutoLab from '../assets/avatars/pluto-lab.svg'
import imgClaude   from '../assets/avatars/claude.svg'
import imgBird     from '../assets/avatars/birdbuddy.png'
import imgPi       from '../assets/avatars/pi.svg'
import imgCloud    from '../assets/avatars/cloud.svg'
import imgCloudStorage from '../assets/avatars/cloud-storage.svg'
import imgSaturn    from '../assets/avatars/saturn.png'
import imgMegadrive from '../assets/avatars/megadrive.png'
import imgSms       from '../assets/avatars/sms.png'
import imgSubstack    from '../assets/avatars/substack.svg'
import imgGoogle      from '../assets/avatars/google.svg'
import imgGateway     from '../assets/avatars/gateway.svg'
import imgRoombaWheel from '../assets/avatars/roomba-wheel.svg'
import imgGamecube from '../assets/avatars/gamecube.png'
import imgGamegear from '../assets/avatars/gamegear.png'
import imgNes      from '../assets/avatars/nes.png'
import imgSnes     from '../assets/avatars/snes.png'
import imgNgp      from '../assets/avatars/ngp.png'
import imgNgpc     from '../assets/avatars/ngpc.png'
import imgGbc      from '../assets/avatars/gbc.png'
import imgPsx      from '../assets/avatars/psx.png'
import imgPs2      from '../assets/avatars/ps2.png'
import imgSys_3ds from '../assets/avatars/3ds.png'
import imgSys_c64 from '../assets/avatars/c64.png'
import imgSys_dos from '../assets/avatars/dos.png'
import imgSys_fds from '../assets/avatars/fds.png'
import imgSys_gb from '../assets/avatars/gb.png'
import imgSys_mame from '../assets/avatars/mame.png'
import imgArcade from '../assets/avatars/arcade.png'
import imgSys_megacd from '../assets/avatars/megacd.png'
import imgSys_msx1 from '../assets/avatars/msx1.png'
import imgSys_n64 from '../assets/avatars/n64.png'
import imgSys_n64dd from '../assets/avatars/n64dd.png'
import imgSys_nds from '../assets/avatars/nds.png'
import imgSys_neogeo from '../assets/avatars/neogeo.png'
import imgSys_neogeocd from '../assets/avatars/neogeocd.png'
import imgSys_pcengine from '../assets/avatars/pcengine.png'
import imgSys_pcenginecd from '../assets/avatars/pcenginecd.png'
import imgSys_pico from '../assets/avatars/pico.png'
import imgSys_pokemini from '../assets/avatars/pokemini.png'
import imgSys_psp from '../assets/avatars/psp.png'
import imgSys_sega32x from '../assets/avatars/sega32x.png'
import imgSys_sufami from '../assets/avatars/sufami.png'
import imgSys_virtualboy from '../assets/avatars/virtualboy.png'
import imgSys_x68000 from '../assets/avatars/x68000.png'
import imgSys_naomi from '../assets/avatars/naomi.png'
import imgSys_ps5 from '../assets/avatars/ps5.png'

export const ICONS: Record<string, string> = {
  wii:       imgWii,
  dc:        imgDc,
  vmu:       imgVmu,
  ps3:       imgPs3,
  gba:       imgGba,
  ws:        imgWs,
  batocera:  imgBatocera,
  dreame:    imgDreame,
  pluto:     imgPlutoC2,    // the live C2 node wears the signal-badge planet mark
  lab:       imgPlutoLab,   // the workspace node wears the beaker-badge planet mark
  saturn:    imgSaturn,
  megadrive: imgMegadrive,
  sms: imgSms,   // Mark III artwork; see avatars/NOTICES
  claude:        imgClaude,
  birdbuddy:     imgBird,
  pi:            imgPi,
  cloud:         imgCloud,
  dropbox:       imgCloudStorage,   // operator-named storage node; generic brandless glyph
  dreamehome:    imgDreame,    // the vacuum's cloud — reuses the Dreame mark
  substack:       imgSubstack,
  google:         imgGoogle,
  gateway:        imgGateway,   // its own signal/router mark — so it doesn't fall back to the guest icon
  'roomba-rally': imgRoombaWheel,
  'crazy-roomba': imgRoombaWheel,
  // system-only icons (Media catalogue tiles; consoles.json systems.<x>.icon)
  gamecube: imgGamecube,
  gamegear: imgGamegear,
  nes: imgNes,
  snes: imgSnes,
  ngp: imgNgp,
  ngpc: imgNgpc,
  gbc: imgGbc,
  psx: imgPsx,
  ps2: imgPs2,
  "3ds": imgSys_3ds,
  c64: imgSys_c64,
  dos: imgSys_dos,
  fds: imgSys_fds,
  gb: imgSys_gb,
  mame: imgSys_mame,
  arcade: imgArcade,   // generic arcade cabinet (FBNeo art) for non-MAME arcade boards
  megacd: imgSys_megacd,
  msx1: imgSys_msx1,
  n64: imgSys_n64,
  n64dd: imgSys_n64dd,
  nds: imgSys_nds,
  neogeo: imgSys_neogeo,
  neogeocd: imgSys_neogeocd,
  pcengine: imgSys_pcengine,
  pcenginecd: imgSys_pcenginecd,
  pico: imgSys_pico,
  pokemini: imgSys_pokemini,
  psp: imgSys_psp,
  sega32x: imgSys_sega32x,
  sufami: imgSys_sufami,
  virtualboy: imgSys_virtualboy,
  x68000: imgSys_x68000,
  naomi: imgSys_naomi,
  ps5: imgSys_ps5,
}
