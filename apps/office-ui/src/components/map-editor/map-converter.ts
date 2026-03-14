/**
 * Bidirectional conversion between internal editor map format and TMJ
 * (Tiled Map JSON). Matches the layer contract from TiledMapLoader.ts:
 * floor, walls, furniture, decorations, collision (tile layers) and
 * departments, review-stations, interactables, spawn-points (object layers).
 */

const TILE_SIZE = 32;

// --- Internal editor types ---------------------------------------------------

export interface EditorLayer {
  name: string;
  data: number[]; // flat array of tile IDs (0 = empty)
  visible: boolean;
}

export interface EditorObject {
  id: string;
  type: 'department' | 'review-station' | 'interactable' | 'spawn-point';
  x: number;
  y: number;
  width: number;
  height: number;
  properties: Record<string, string | number | boolean>;
}

export interface EditorMap {
  width: number;   // tiles
  height: number;  // tiles
  tileWidth: number;
  tileHeight: number;
  layers: EditorLayer[];
  objects: EditorObject[];
}

// --- TMJ types (subset matching tmj-writer.ts) --------------------------------

interface TmjProperty {
  name: string;
  type: string;
  value: string | number | boolean;
}

interface TmjObject {
  id: number;
  name: string;
  type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  properties?: TmjProperty[];
  visible: boolean;
}

interface TmjLayer {
  id: number;
  name: string;
  type: 'tilelayer' | 'objectgroup';
  x: number;
  y: number;
  width?: number;
  height?: number;
  data?: number[];
  objects?: TmjObject[];
  visible: boolean;
  opacity: number;
}

// Known tile layer names (must paint in this order)
const TILE_LAYER_NAMES = ['floor', 'walls', 'furniture', 'decorations', 'collision'] as const;

// Known object layer names with mapping to EditorObject type
const OBJECT_LAYER_MAP: Record<string, EditorObject['type']> = {
  'departments': 'department',
  'review-stations': 'review-station',
  'interactables': 'interactable',
  'spawn-points': 'spawn-point',
};

// --- Conversion: internal -> TMJ ---------------------------------------------

let nextObjectId = 1;

function editorObjectToTmj(obj: EditorObject): TmjObject {
  const props: TmjProperty[] = Object.entries(obj.properties).map(([name, value]) => ({
    name,
    type: typeof value === 'number' ? 'int' : typeof value === 'boolean' ? 'bool' : 'string',
    value,
  }));

  return {
    id: nextObjectId++,
    name: obj.properties.name as string || obj.type,
    type: '',
    x: obj.x,
    y: obj.y,
    width: obj.width,
    height: obj.height,
    properties: props.length > 0 ? props : undefined,
    visible: true,
  };
}

export function internalToTmj(map: EditorMap): object {
  nextObjectId = 1;
  let layerId = 1;

  const layers: TmjLayer[] = [];

  // Add tile layers
  for (const layerName of TILE_LAYER_NAMES) {
    const editorLayer = map.layers.find((l) => l.name === layerName);
    layers.push({
      id: layerId++,
      name: layerName,
      type: 'tilelayer',
      x: 0,
      y: 0,
      width: map.width,
      height: map.height,
      data: editorLayer ? [...editorLayer.data] : new Array(map.width * map.height).fill(0),
      visible: editorLayer?.visible ?? true,
      opacity: 1,
    });
  }

  // Add object layers
  for (const [layerName, objType] of Object.entries(OBJECT_LAYER_MAP)) {
    const objs = map.objects.filter((o) => o.type === objType);
    layers.push({
      id: layerId++,
      name: layerName,
      type: 'objectgroup',
      x: 0,
      y: 0,
      objects: objs.map(editorObjectToTmj),
      visible: true,
      opacity: 1,
    });
  }

  return {
    compressionlevel: -1,
    height: map.height,
    width: map.width,
    infinite: false,
    layers,
    nextlayerid: layerId,
    nextobjectid: nextObjectId,
    orientation: 'orthogonal',
    renderorder: 'right-down',
    tileheight: map.tileHeight,
    tilewidth: map.tileWidth,
    tilesets: [
      {
        firstgid: 1,
        name: 'office-tileset',
        tilewidth: map.tileWidth,
        tileheight: map.tileHeight,
        tilecount: 54,
        columns: 16,
        image: '../tilesets/office-tileset.png',
        imagewidth: 512,
        imageheight: 128,
      },
    ],
    type: 'map',
    version: '1.10',
    tiledversion: '1.11.0',
  };
}

// --- Conversion: TMJ -> internal ---------------------------------------------

function tmjObjectToEditor(
  obj: TmjObject,
  objType: EditorObject['type'],
  idCounter: { value: number },
): EditorObject {
  const properties: Record<string, string | number | boolean> = {};
  if (obj.properties) {
    for (const prop of obj.properties) {
      properties[prop.name] = prop.value;
    }
  }
  if (obj.name) {
    properties.name = obj.name;
  }

  return {
    id: `obj_${idCounter.value++}`,
    type: objType,
    x: obj.x,
    y: obj.y,
    width: obj.width,
    height: obj.height,
    properties,
  };
}

export function tmjToInternal(tmj: object): EditorMap {
  const data = tmj as Record<string, unknown>;
  const width = (data.width as number) || 10;
  const height = (data.height as number) || 10;
  const tileWidth = (data.tilewidth as number) || TILE_SIZE;
  const tileHeight = (data.tileheight as number) || TILE_SIZE;
  const tmjLayers = (data.layers as TmjLayer[]) || [];

  const layers: EditorLayer[] = [];
  const objects: EditorObject[] = [];
  const idCounter = { value: 1 };

  for (const tmjLayer of tmjLayers) {
    if (tmjLayer.type === 'tilelayer') {
      layers.push({
        name: tmjLayer.name,
        data: tmjLayer.data ? [...tmjLayer.data] : new Array(width * height).fill(0),
        visible: tmjLayer.visible,
      });
    } else if (tmjLayer.type === 'objectgroup') {
      const objType = OBJECT_LAYER_MAP[tmjLayer.name];
      if (objType && tmjLayer.objects) {
        for (const tmjObj of tmjLayer.objects) {
          objects.push(tmjObjectToEditor(tmjObj, objType, idCounter));
        }
      }
    }
  }

  // Ensure all tile layers exist (fill missing ones with empty data)
  for (const layerName of TILE_LAYER_NAMES) {
    if (!layers.find((l) => l.name === layerName)) {
      layers.push({
        name: layerName,
        data: new Array(width * height).fill(0),
        visible: true,
      });
    }
  }

  return {
    width,
    height,
    tileWidth,
    tileHeight,
    layers,
    objects,
  };
}

// --- Helpers -----------------------------------------------------------------

export function createEmptyMap(width = 20, height = 15): EditorMap {
  const size = width * height;
  return {
    width,
    height,
    tileWidth: TILE_SIZE,
    tileHeight: TILE_SIZE,
    layers: TILE_LAYER_NAMES.map((name) => ({
      name,
      data: new Array(size).fill(0),
      visible: true,
    })),
    objects: [],
  };
}
