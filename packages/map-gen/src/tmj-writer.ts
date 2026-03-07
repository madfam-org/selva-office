/**
 * TMJ (Tiled Map JSON) writer.
 *
 * Outputs .tmj files that conform to the same schema expected by
 * TiledMapLoader.ts: floor layer, departments object layer,
 * review-stations object layer, spawn-points object layer,
 * and interactables object layer.
 */

import type { MetaTile } from './wfc';
import type { DepartmentRegion, PlacedObject } from './constraints';
import { metaTileToTileId } from './rules';

const TILE_SIZE = 32;

interface TmjTileset {
  firstgid: number;
  source?: string;
  name: string;
  tilewidth: number;
  tileheight: number;
  tilecount: number;
  columns: number;
  image: string;
  imagewidth: number;
  imageheight: number;
}

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

export interface TmjMap {
  compressionlevel: number;
  height: number;
  width: number;
  infinite: boolean;
  layers: TmjLayer[];
  nextlayerid: number;
  nextobjectid: number;
  orientation: string;
  renderorder: string;
  tileheight: number;
  tilewidth: number;
  tilesets: TmjTileset[];
  type: string;
  version: string;
  tiledversion: string;
}

/**
 * Convert a WFC meta-tile grid + placed objects into a valid .tmj file.
 */
export function buildTmj(
  grid: MetaTile[][],
  regions: DepartmentRegion[],
  objects: PlacedObject[],
): TmjMap {
  const height = grid.length;
  const width = grid[0].length;

  // Build floor tile data (1-indexed for Tiled, +1 because firstgid=1)
  const floorData: number[] = [];
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      floorData.push(metaTileToTileId(grid[y][x]) + 1);
    }
  }

  let nextObjectId = 1;

  // Department objects
  const deptObjects: TmjObject[] = regions.map((region) => ({
    id: nextObjectId++,
    name: region.name,
    type: '',
    x: region.bounds.x * TILE_SIZE,
    y: region.bounds.y * TILE_SIZE,
    width: region.bounds.width * TILE_SIZE,
    height: region.bounds.height * TILE_SIZE,
    properties: [
      { name: 'slug', type: 'string', value: region.slug },
      { name: 'name', type: 'string', value: region.name },
      { name: 'color', type: 'string', value: region.color },
      { name: 'maxAgents', type: 'int', value: 4 },
    ],
    visible: true,
  }));

  // Review station objects
  const reviewObjects: TmjObject[] = objects
    .filter((o) => o.type === 'review-station')
    .map((o) => ({
      id: nextObjectId++,
      name: 'review-station',
      type: '',
      x: o.x * TILE_SIZE,
      y: o.y * TILE_SIZE,
      width: TILE_SIZE,
      height: TILE_SIZE,
      properties: [
        { name: 'departmentSlug', type: 'string', value: o.properties.departmentSlug as string },
      ],
      visible: true,
    }));

  // Interactable objects (dispatch stations)
  const interactableObjects: TmjObject[] = objects
    .filter((o) => o.type === 'dispatch')
    .map((o) => ({
      id: nextObjectId++,
      name: 'dispatch-station',
      type: '',
      x: o.x * TILE_SIZE,
      y: o.y * TILE_SIZE,
      width: TILE_SIZE,
      height: TILE_SIZE,
      properties: [
        { name: 'interactType', type: 'string', value: 'dispatch' },
        { name: 'label', type: 'string', value: 'Dispatch Task' },
      ],
      visible: true,
    }));

  // Spawn point objects
  const spawnObjects: TmjObject[] = objects
    .filter((o) => o.type === 'spawn-point')
    .map((o) => ({
      id: nextObjectId++,
      name: o.properties.name as string,
      type: '',
      x: o.x * TILE_SIZE,
      y: o.y * TILE_SIZE,
      width: TILE_SIZE,
      height: TILE_SIZE,
      visible: true,
    }));

  const layers: TmjLayer[] = [
    {
      id: 1,
      name: 'floor',
      type: 'tilelayer',
      x: 0,
      y: 0,
      width,
      height,
      data: floorData,
      visible: true,
      opacity: 1,
    },
    {
      id: 2,
      name: 'departments',
      type: 'objectgroup',
      x: 0,
      y: 0,
      objects: deptObjects,
      visible: true,
      opacity: 1,
    },
    {
      id: 3,
      name: 'review-stations',
      type: 'objectgroup',
      x: 0,
      y: 0,
      objects: reviewObjects,
      visible: true,
      opacity: 1,
    },
    {
      id: 4,
      name: 'interactables',
      type: 'objectgroup',
      x: 0,
      y: 0,
      objects: interactableObjects,
      visible: true,
      opacity: 1,
    },
    {
      id: 5,
      name: 'spawn-points',
      type: 'objectgroup',
      x: 0,
      y: 0,
      objects: spawnObjects,
      visible: true,
      opacity: 1,
    },
  ];

  return {
    compressionlevel: -1,
    height,
    width,
    infinite: false,
    layers,
    nextlayerid: layers.length + 1,
    nextobjectid: nextObjectId,
    orientation: 'orthogonal',
    renderorder: 'right-down',
    tileheight: TILE_SIZE,
    tilewidth: TILE_SIZE,
    tilesets: [
      {
        firstgid: 1,
        name: 'office-tileset',
        tilewidth: TILE_SIZE,
        tileheight: TILE_SIZE,
        tilecount: 8,
        columns: 8,
        image: '../tilesets/office-tileset.png',
        imagewidth: 256,
        imageheight: 32,
      },
    ],
    type: 'map',
    version: '1.10',
    tiledversion: '1.11.0',
  };
}
