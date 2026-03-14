import { Schema, type, ArraySchema } from "@colyseus/schema";

export class StrokeSchema extends Schema {
  @type("number") x: number = 0;
  @type("number") y: number = 0;
  @type("number") toX: number = 0;
  @type("number") toY: number = 0;
  @type("string") color: string = "#ffffff";
  @type("number") width: number = 2;
  @type("string") tool: string = "pen";
  @type("string") senderId: string = "";
}

export class WhiteboardSchema extends Schema {
  @type("string") id: string = "";
  @type([StrokeSchema]) strokes: ArraySchema<StrokeSchema> =
    new ArraySchema<StrokeSchema>();
}
