# # server/main.py
# import asyncio
# import json
# import math
# import heapq
# import random
# from typing import List, Tuple, Dict
# from fastapi import FastAPI, WebSocket, WebSocketDisconnect
# import uvicorn

# app = FastAPI()

# # CONFIG
# GRID_W = 20
# GRID_H = 14
# TICK_DT = 0.08  # seconds per server tick
# REPLAN_INTERVAL = 0.3  # seconds between A* replans for each AI

# # Utilities
# def in_bounds(x, y):
#     return 0 <= x < GRID_W and 0 <= y < GRID_H

# # Build grid (0 = free, 1 = wall)
# grid = [[0 for _ in range(GRID_W)] for _ in range(GRID_H)]
# # Random obstacles for quick demo
# random.seed(1)
# for _ in range(int(GRID_W * GRID_H * 0.18)):
#     x = random.randrange(GRID_W)
#     y = random.randrange(GRID_H)
#     grid[y][x] = 1

# # ensure some free area
# for y in range(GRID_H):
#     for x in range(GRID_W):
#         if (x == 0 or y == 0 or x == GRID_W-1 or y == GRID_H-1):
#             grid[y][x] = 1  # border walls

# # Helper: neighbors (4-dir)
# dirs = [(0,-1),(1,0),(0,1),(-1,0)]
# def neighbors(node):
#     x,y = node
#     for dx,dy in dirs:
#         nx,ny = x+dx, y+dy
#         if in_bounds(nx,ny) and grid[ny][nx] == 0:
#             yield (nx,ny)

# # A* implementation (returns list of (x,y) from start to goal inclusive or empty)
# def heuristic(a, b):
#     return abs(a[0]-b[0]) + abs(a[1]-b[1])

# def astar(start:Tuple[int,int], goal:Tuple[int,int]) -> List[Tuple[int,int]]:
#     if start == goal:
#         return [start]
#     open_heap = []
#     heapq.heappush(open_heap, (0 + heuristic(start,goal), 0, start))
#     came_from = {}
#     gscore = {start: 0}
#     closed = set()
#     while open_heap:
#         f, g, current = heapq.heappop(open_heap)
#         if current == goal:
#             # reconstruct
#             path = [current]
#             while current in came_from:
#                 current = came_from[current]
#                 path.append(current)
#             return list(reversed(path))
#         closed.add(current)
#         for n in neighbors(current):
#             if n in closed:
#                 continue
#             tentative_g = gscore[current] + 1
#             if tentative_g < gscore.get(n, 10**9):
#                 came_from[n] = current
#                 gscore[n] = tentative_g
#                 heapq.heappush(open_heap, (tentative_g + heuristic(n,goal), tentative_g, n))
#     return []

# # Game state
# state = {
#     "player": {"x": 2.0, "y": 2.0, "vx":0.0, "vy":0.0},
#     "enemies": [],  # list of dicts: id,x,y,state,path,last_replan_time
#     "coins": []
# }

# # spawn one enemy and some coins
# state["enemies"].append({"id":1, "x": GRID_W-3 + 0.0, "y": GRID_H-3 + 0.0, "state":"patrol", "path":[], "last_replan":0.0, "last_seen": None})
# for _ in range(8):
#     while True:
#         x = random.randrange(1, GRID_W-1)
#         y = random.randrange(1, GRID_H-1)
#         if grid[y][x] == 0 and (x,y) != (int(state["player"]["x"]), int(state["player"]["y"])):
#             state["coins"].append({"x":x,"y":y})
#             break

# # Websocket connection manager
# class ConnectionManager:
#     def __init__(self):
#         self.connections: List[WebSocket] = []
#     async def connect(self, ws: WebSocket):
#         await ws.accept()
#         self.connections.append(ws)
#     def disconnect(self, ws: WebSocket):
#         if ws in self.connections:
#             self.connections.remove(ws)
#     async def broadcast(self, msg: dict):
#         data = json.dumps(msg)
#         for ws in list(self.connections):
#             try:
#                 await ws.send_text(data)
#             except:
#                 self.disconnect(ws)

# manager = ConnectionManager()

# @app.websocket("/ws")
# async def websocket_endpoint(ws: WebSocket):
#     await manager.connect(ws)
#     try:
#         # send initial grid and state
#         await ws.send_text(json.dumps({"type":"init","grid":grid,"state":state}))
#         while True:
#             text = await ws.receive_text()
#             # expecting inputs as json: {"type":"input","dx":-1/0/1,"dy":...}
#             try:
#                 msg = json.loads(text)
#                 if msg.get("type") == "input":
#                     # update player's velocity (simple)
#                     dx = msg.get("dx",0)
#                     dy = msg.get("dy",0)
#                     speed = 5.0  # tiles per second
#                     state["player"]["vx"] = dx * speed
#                     state["player"]["vy"] = dy * speed
#             except Exception as e:
#                 print("bad msg", e)
#     except WebSocketDisconnect:
#         manager.disconnect(ws)

# # Game loop
# async def game_loop():
#     t = 0.0
#     while True:
#         # 1) advance physics / player
#         px = state["player"]["x"]
#         py = state["player"]["y"]
#         vx = state["player"]["vx"]
#         vy = state["player"]["vy"]
#         # move by dt in tile coords
#         new_px = px + vx * TICK_DT
#         new_py = py + vy * TICK_DT
#         # clamp and prevent walking into walls (simple)
#         def can_move_to(xf,yf):
#             cx = int(round(xf))
#             cy = int(round(yf))
#             return in_bounds(cx,cy) and grid[cy][cx] == 0
#         if can_move_to(new_px, py):
#             state["player"]["x"] = new_px
#         if can_move_to(state["player"]["x"], new_py):
#             state["player"]["y"] = new_py

#         # Tick enemies: each enemy tries to chase player using A*
#         for e in state["enemies"]:
#             ex = e["x"]
#             ey = e["y"]
#             eid = e["id"]
#             # detection: simple distance <= 6 tiles => see player
#             pdx = int(round(state["player"]["x"]))
#             pdy = int(round(state["player"]["y"]))
#             edx = int(round(ex))
#             edy = int(round(ey))
#             dist = abs(pdx - edx) + abs(pdy - edy)
#             see = (dist <= 6)
#             # Replan if we see player and enough time passed
#             if see:
#                 e["last_seen"] = (pdx,pdy)
#                 if t - e["last_replan"] > REPLAN_INTERVAL:
#                     path = astar((int(round(ex)),int(round(ey))),(pdx,pdy))
#                     if path:
#                         e["path"] = path
#                     e["last_replan"] = t
#                     e["state"] = "chase"
#             else:
#                 # if we had last_seen, go search there
#                 if e.get("last_seen"):
#                     target = e["last_seen"]
#                     if (int(round(ex)),int(round(ey))) == target:
#                         # reached search spot
#                         e["last_seen"] = None
#                         e["path"] = []
#                         e["state"] = "patrol"
#                     else:
#                         if t - e["last_replan"] > REPLAN_INTERVAL:
#                             path = astar((int(round(ex)),int(round(ey))), target)
#                             e["path"] = path
#                             e["last_replan"] = t
#                             e["state"] = "search"
#                 else:
#                     # simple patrol: stay put or wander slowly
#                     if random.random() < 0.02:
#                         # pick random nearby free tile
#                         for _ in range(10):
#                             rx = int(round(ex)) + random.randint(-3,3)
#                             ry = int(round(ey)) + random.randint(-3,3)
#                             if in_bounds(rx,ry) and grid[ry][rx] == 0:
#                                 e["path"] = astar((int(round(ex)),int(round(ey))),(rx,ry))
#                                 e["state"] = "patrol"
#                                 break

#             # Follow path a bit (move at speed)
#             if e["path"]:
#                 # path is list of tiles; next tile index 1 is next (0 is current)
#                 next_idx = 1 if len(e["path"]) > 1 else 0
#                 nx,ny = e["path"][next_idx]
#                 # move toward nx,ny by small step
#                 exf = ex + (nx - ex) * 0.4  # smoothing factor
#                 eyf = ey + (ny - ey) * 0.4
#                 # prevent moving into wall center
#                 if grid[int(round(eyf))][int(round(exf))] == 0:
#                     e["x"] = exf
#                     e["y"] = eyf
#                 # if close to the next tile, drop the first node
#                 if abs(e["x"] - nx) < 0.4 and abs(e["y"] - ny) < 0.4 and len(e["path"])>1:
#                     e["path"].pop(0)
#             else:
#                 # slight idle jitter
#                 e["x"] += (random.random()-0.5) * 0.02
#                 e["y"] += (random.random()-0.5) * 0.02

#             # If enemy reaches player tile -> "caught": reset player
#             if int(round(e["x"])) == int(round(state["player"]["x"])) and int(round(e["y"])) == int(round(state["player"]["y"])):
#                 # move player back to spawn
#                 state["player"]["x"] = 2.0
#                 state["player"]["y"] = 2.0
#                 state["player"]["vx"] = 0.0
#                 state["player"]["vy"] = 0.0

#         # Collect coins
#         pxi = int(round(state["player"]["x"]))
#         pyi = int(round(state["player"]["y"]))
#         new_coins = []
#         for c in state["coins"]:
#             if not (c["x"] == pxi and c["y"] == pyi):
#                 new_coins.append(c)
#         if len(new_coins) != len(state["coins"]):
#             state["coins"] = new_coins

#         # broadcast state snapshot every tick
#         await manager.broadcast({"type":"state","tick":t,"state":state})
#         await asyncio.sleep(TICK_DT)
#         t += TICK_DT

# # Startup: launch game loop in background
# @app.on_event("startup")
# async def startup_event():
#     asyncio.create_task(game_loop())

# if __name__ == "__main__":
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)










































# # server/main.py
# """
# Advanced demo server for AI-chase game.
# FastAPI + WebSocket authoritative server running A* + simple AI FSM per enemy.
# Drop-in replacement for the earlier demo.
# """
# import asyncio, json, math, heapq, random, time
# from typing import List, Tuple
# from fastapi import FastAPI, WebSocket, WebSocketDisconnect
# import uvicorn

# app = FastAPI()

# # === CONFIG ===
# GRID_W = 28
# GRID_H = 18
# TICK_DT = 0.06
# REPLAN_INTERVAL = 0.25
# ENEMY_SPEED = 2.8        # tiles per second
# PLAYER_SPEED = 6.0       # tiles per second
# ENEMY_COUNT = 3
# DETECTION_RANGE = 7      # tiles (manhattan approx)
# MISSION_COINS = 8
# MISSION_TIME = 120       # seconds

# # === GRID & UTILITIES ===
# def in_bounds(x,y): return 0 <= x < GRID_W and 0 <= y < GRID_H

# # create a grid with borders and some obstacles
# grid = [[0 for _ in range(GRID_W)] for _ in range(GRID_H)]
# random.seed(2)
# # border walls
# for x in range(GRID_W):
#     grid[0][x] = grid[GRID_H-1][x] = 1
# for y in range(GRID_H):
#     grid[y][0] = grid[y][GRID_W-1] = 1
# # random blocks
# for _ in range(int(GRID_W*GRID_H*0.18)):
#     x = random.randrange(1, GRID_W-1)
#     y = random.randrange(1, GRID_H-1)
#     grid[y][x] = 1

# dirs4 = [(0,-1),(1,0),(0,1),(-1,0)]
# def neighbors(node):
#     x,y = node
#     for dx,dy in dirs4:
#         nx,ny = x+dx, y+dy
#         if in_bounds(nx,ny) and grid[ny][nx] == 0:
#             yield (nx,ny)

# def heuristic(a,b):
#     return abs(a[0]-b[0]) + abs(a[1]-b[1])

# def astar(start:Tuple[int,int], goal:Tuple[int,int]) -> List[Tuple[int,int]]:
#     """A* returning list of (x,y) inclusive, empty list if fail."""
#     start = (int(start[0]), int(start[1]))
#     goal = (int(goal[0]), int(goal[1]))
#     if start == goal:
#         return [start]
#     open_heap = []
#     heapq.heappush(open_heap, (heuristic(start,goal), 0, start))
#     came_from = {}
#     gscore = {start:0}
#     closed = set()
#     while open_heap:
#         f,g,current = heapq.heappop(open_heap)
#         if current == goal:
#             path = [current]
#             while current in came_from:
#                 current = came_from[current]
#                 path.append(current)
#             return list(reversed(path))
#         closed.add(current)
#         for n in neighbors(current):
#             if n in closed: continue
#             tentative = gscore[current] + 1
#             if tentative < gscore.get(n, 1e9):
#                 came_from[n] = current
#                 gscore[n] = tentative
#                 heapq.heappush(open_heap, (tentative + heuristic(n,goal), tentative, n))
#     return []

# # Bresenham line for LOS (grid raycast)
# def bresenham_line(a:Tuple[int,int], b:Tuple[int,int]):
#     x0,y0 = a; x1,y1 = b
#     dx = abs(x1-x0); dy = -abs(y1-y0)
#     sx = 1 if x0<x1 else -1
#     sy = 1 if y0<y1 else -1
#     err = dx+dy
#     x,y = x0,y0
#     pts = []
#     while True:
#         pts.append((x,y))
#         if x==x1 and y==y1: break
#         e2 = 2*err
#         if e2 >= dy:
#             err += dy; x += sx
#         if e2 <= dx:
#             err += dx; y += sy
#     return pts

# def line_of_sight(a,b):
#     for (x,y) in bresenham_line(a,b):
#         if not in_bounds(x,y): return False
#         if grid[y][x] == 1 and (x,y) != a and (x,y) != b:
#             return False
#     return True

# # === GAME STATE ===
# game = {
#     "player": {"x":2.5,"y":2.5,"vx":0.0,"vy":0.0},
#     "enemies": [],
#     "coins": [],
#     "score":0,
#     "mission": {"coins_needed": MISSION_COINS, "coins_collected":0, "time_left": MISSION_TIME, "running": True}
# }

# # spawn coins
# def spawn_coins(n):
#     game["coins"].clear()
#     tries=0
#     while len(game["coins"])<n and tries<1000:
#         tries+=1
#         x = random.randrange(1, GRID_W-1); y = random.randrange(1, GRID_H-1)
#         if grid[y][x] == 0 and (abs(x-int(game["player"]["x"]))>1 or abs(y-int(game["player"]["y"]))>1):
#             if not any(c["x"]==x and c["y"]==y for c in game["coins"]):
#                 game["coins"].append({"x":x,"y":y})
# spawn_coins(MISSION_COINS)

# # create enemies
# def spawn_enemies(n):
#     game["enemies"].clear()
#     for i in range(n):
#         # find free tile
#         for _ in range(400):
#             x = random.randrange(1, GRID_W-1); y = random.randrange(1, GRID_H-1)
#             if grid[y][x]==0 and (abs(x-int(game["player"]["x"]))>3 or abs(y-int(game["player"]["y"]))>3):
#                 ent = {
#                     "id": i+1,
#                     "x": float(x),
#                     "y": float(y),
#                     "state": "patrol",
#                     "path": [],
#                     "last_replan": 0.0,
#                     "last_seen": None,
#                     "patrol_target": None
#                 }
#                 game["enemies"].append(ent)
#                 break
# spawn_enemies(ENEMY_COUNT)

# # === WEBSOCKET CONNECTION MANAGER ===
# class ConnectionManager:
#     def __init__(self): self.connections = []
#     async def connect(self, ws: WebSocket):
#         await ws.accept(); self.connections.append(ws)
#     def disconnect(self, ws: WebSocket):
#         if ws in self.connections: self.connections.remove(ws)
#     async def broadcast(self, msg: dict):
#         data = json.dumps(msg)
#         for ws in list(self.connections):
#             try:
#                 await ws.send_text(data)
#             except:
#                 self.disconnect(ws)

# manager = ConnectionManager()

# @app.websocket("/ws")
# async def ws_endpoint(ws: WebSocket):
#     await manager.connect(ws)
#     try:
#         # initial snapshot with grid
#         await ws.send_text(json.dumps({"type":"init","grid":grid,"state":game}))
#         while True:
#             text = await ws.receive_text()
#             try:
#                 msg = json.loads(text)
#                 if msg.get("type")=="input":
#                     dx = int(msg.get("dx",0)); dy = int(msg.get("dy",0))
#                     # normalize diagonal
#                     if dx!=0 and dy!=0:
#                         norm = math.sqrt(2)/2
#                         dx *= norm; dy *= norm
#                     game["player"]["vx"] = dx * PLAYER_SPEED
#                     game["player"]["vy"] = dy * PLAYER_SPEED
#                 elif msg.get("type") == "reset":
#                     game["player"]["x"] = 2.5; game["player"]["y"]=2.5
#             except Exception as e:
#                 print("bad msg:", e)
#     except WebSocketDisconnect:
#         manager.disconnect(ws)

# # === AI / GAME LOOP ===
# async def game_loop():
#     t = 0.0
#     last_time = time.time()
#     while True:
#         now = time.time()
#         dt = TICK_DT  # fixed tick for determinism
#         t += dt

#         # --- player movement & collision ---
#         px = game["player"]["x"]; py = game["player"]["y"]
#         vx = game["player"]["vx"]; vy = game["player"]["vy"]
#         nx = px + vx * dt; ny = py + vy * dt
#         # simple collision: only allow move if target tile is free
#         def can_at(xf,yf):
#             xi, yi = int(round(xf)), int(round(yf))
#             return in_bounds(xi,yi) and grid[yi][xi]==0
#         if can_at(nx, py): game["player"]["x"]=nx
#         if can_at(game["player"]["x"], ny): game["player"]["y"]=ny

#         # --- enemies AI ---
#         player_tile = (int(round(game["player"]["x"])), int(round(game["player"]["y"])))
#         player_vel = (game["player"]["vx"], game["player"]["vy"])

#         for e in game["enemies"]:
#             exf, eyf = e["x"], e["y"]
#             e_tile = (int(round(exf)), int(round(eyf)))
#             manh = abs(e_tile[0]-player_tile[0]) + abs(e_tile[1]-player_tile[1])
#             sees = False
#             if manh <= DETECTION_RANGE and line_of_sight(e_tile, player_tile):
#                 sees = True

#             # if sees player -> record last seen and chase
#             if sees:
#                 e["last_seen"] = player_tile
#                 e["state"] = "chase"
#             # Replanning logic
#             if e["state"] == "chase":
#                 # predicted intercept: lead by a short time
#                 lead_time = max(0.2, manh/6.0)  # short lead depending on distance
#                 target_x = int(round(game["player"]["x"] + player_vel[0]*lead_time))
#                 target_y = int(round(game["player"]["y"] + player_vel[1]*lead_time))
#                 target_tile = (max(1,min(GRID_W-2,target_x)), max(1,min(GRID_H-2,target_y)))
#                 if t - e["last_replan"] > REPLAN_INTERVAL:
#                     path = astar(e_tile, target_tile)
#                     if path:
#                         e["path"] = path
#                     e["last_replan"] = t
#             elif e["state"] == "search":
#                 if e.get("last_seen"):
#                     if e_tile == e["last_seen"]:
#                         # arrived to last seen
#                         e["last_seen"] = None
#                         e["path"] = []
#                         e["state"] = "patrol"
#                     else:
#                         if t - e["last_replan"] > REPLAN_INTERVAL:
#                             e["path"] = astar(e_tile, e["last_seen"])
#                             e["last_replan"] = t
#                 else:
#                     e["state"] = "patrol"
#             elif e["state"] == "patrol":
#                 # ensure patrol_target exists
#                 if not e.get("patrol_target") or e_tile == e["patrol_target"]:
#                     # pick random nearby tile
#                     for _ in range(15):
#                         rx = e_tile[0] + random.randint(-6,6)
#                         ry = e_tile[1] + random.randint(-6,6)
#                         if in_bounds(rx,ry) and grid[ry][rx]==0:
#                             e["patrol_target"] = (rx,ry)
#                             e["path"] = astar(e_tile, e["patrol_target"])
#                             break

#             # if no sees but have last seen and currently patrol -> go search
#             if not sees and e.get("last_seen") and e["state"]!="search":
#                 e["state"] = "search"

#             # follow path: compute movement toward next waypoint
#             if e["path"] and len(e["path"])>0:
#                 # find next node index. path[0] might be the current tile, so pick index 1 if present.
#                 idx = 1 if len(e["path"])>1 else 0
#                 nx_tile = e["path"][idx]
#                 # desired vector toward tile center
#                 target_cx = nx_tile[0] + 0.5
#                 target_cy = nx_tile[1] + 0.5
#                 dirx = target_cx - exf
#                 diry = target_cy - eyf
#                 dist = math.hypot(dirx,diry) or 1e-6
#                 step = ENEMY_SPEED * dt
#                 mx = (dirx/dist) * min(step, dist)
#                 my = (diry/dist) * min(step, dist)
#                 candx = exf + mx
#                 candy = eyf + my
#                 # if center of candidate tile is free
#                 if in_bounds(int(round(candx)), int(round(candy))) and grid[int(round(candy))][int(round(candx))]==0:
#                     e["x"] = candx; e["y"] = candy
#                 # pop path head when reached next node center
#                 if abs(e["x"] - (nx_tile[0]+0.5)) < 0.35 and abs(e["y"] - (nx_tile[1]+0.5)) < 0.35:
#                     if len(e["path"])>1:
#                         e["path"].pop(0)
#             else:
#                 # idle jitter
#                 e["x"] += (random.random()-0.5)*0.02
#                 e["y"] += (random.random()-0.5)*0.02

#             # collision with player -> caught
#             if int(round(e["x"])) == int(round(game["player"]["x"])) and int(round(e["y"])) == int(round(game["player"]["y"])):
#                 # reset player and reduce score slightly
#                 game["player"]["x"] = 2.5; game["player"]["y"]=2.5
#                 game["player"]["vx"] = 0.0; game["player"]["vy"] = 0.0
#                 game["score"] = max(0, game["score"] - 1)
#                 # enemy goes to patrol after catch
#                 e["path"] = []
#                 e["state"] = "patrol"
#                 e["last_seen"] = None

#         # --- coin collection & mission timer ---
#         pxi, pyi = int(round(game["player"]["x"])), int(round(game["player"]["y"]))
#         removed = False
#         for c in list(game["coins"]):
#             if c["x"]==pxi and c["y"]==pyi:
#                 game["coins"].remove(c)
#                 game["score"] += 1
#                 game["mission"]["coins_collected"] += 1
#                 removed = True
#         # mission timer
#         if game["mission"]["running"]:
#             game["mission"]["time_left"] = max(0, game["mission"]["time_left"] - dt)
#             if game["mission"]["coins_collected"] >= game["mission"]["coins_needed"]:
#                 game["mission"]["running"] = False
#             elif game["mission"]["time_left"] <= 0:
#                 game["mission"]["running"] = False

#         # broadcast concise snapshot
#         snapshot = {
#             "type":"state",
#             "tick": t,
#             "state": {
#                 "player": game["player"],
#                 "enemies": [
#                     {
#                         "id": e["id"],
#                         "x": e["x"],
#                         "y": e["y"],
#                         "state": e["state"],
#                         "path": e["path"][:10],   # send small path prefix
#                         "last_seen": e.get("last_seen")
#                     } for e in game["enemies"]
#                 ],
#                 "coins": game["coins"],
#                 "score": game["score"],
#                 "mission": game["mission"]
#             }
#         }
#         await manager.broadcast(snapshot)
#         await asyncio.sleep(dt)

# @app.on_event("startup")
# async def start_loop():
#     asyncio.create_task(game_loop())

# if __name__ == "__main__":
#     uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)












































# server/main.py
"""
Advanced continuous-tracking AI server.
Replace your existing server/main.py with this file.
"""
import asyncio, json, math, heapq, random, time
from typing import List, Tuple
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

# === CONFIG ===
GRID_W = 28
GRID_H = 18
TICK_DT = 0.06
REPLAN_INTERVAL = 0.22
ENEMY_SPEED = 2.8        # tiles per second
PLAYER_SPEED = 6.0       # tiles per second
ENEMY_COUNT = 4
MISSION_COINS = 8
MISSION_TIME = 120       # seconds

# === GRID & UTILITIES ===
def in_bounds(x,y): return 0 <= x < GRID_W and 0 <= y < GRID_H

# create a grid with borders and some obstacles
grid = [[0 for _ in range(GRID_W)] for _ in range(GRID_H)]
random.seed(2)
# border walls
for x in range(GRID_W):
    grid[0][x] = grid[GRID_H-1][x] = 1
for y in range(GRID_H):
    grid[y][0] = grid[y][GRID_W-1] = 1
# random blocks
for _ in range(int(GRID_W*GRID_H*0.18)):
    x = random.randrange(1, GRID_W-1)
    y = random.randrange(1, GRID_H-1)
    grid[y][x] = 1

dirs4 = [(0,-1),(1,0),(0,1),(-1,0)]
def neighbors(node):
    x,y = node
    for dx,dy in dirs4:
        nx,ny = x+dx, y+dy
        if in_bounds(nx,ny) and grid[ny][nx] == 0:
            yield (nx,ny)

def heuristic(a,b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1])

def astar(start:Tuple[int,int], goal:Tuple[int,int]) -> List[Tuple[int,int]]:
    start = (int(start[0]), int(start[1]))
    goal = (int(goal[0]), int(goal[1]))
    if start == goal:
        return [start]
    open_heap = []
    heapq.heappush(open_heap, (heuristic(start,goal), 0, start))
    came_from = {}
    gscore = {start:0}
    closed = set()
    while open_heap:
        f,g,current = heapq.heappop(open_heap)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return list(reversed(path))
        closed.add(current)
        for n in neighbors(current):
            if n in closed: continue
            tentative = gscore[current] + 1
            if tentative < gscore.get(n, 1e9):
                came_from[n] = current
                gscore[n] = tentative
                heapq.heappush(open_heap, (tentative + heuristic(n,goal), tentative, n))
    return []

# === GAME STATE MANAGEMENT ===
def make_game_state():
    return {
        "player": {"x":2.5,"y":2.5,"vx":0.0,"vy":0.0},
        "enemies": [],
        "coins": [],
        "score":0,
        "mission": {"coins_needed": MISSION_COINS, "coins_collected":0, "time_left": MISSION_TIME, "running": True},
        "game_over": False
    }

game = make_game_state()

def spawn_coins(n):
    game["coins"].clear()
    tries=0
    while len(game["coins"])<n and tries<2000:
        tries+=1
        x = random.randrange(1, GRID_W-1); y = random.randrange(1, GRID_H-1)
        if grid[y][x] == 0 and (abs(x-int(game["player"]["x"]))>1 or abs(y-int(game["player"]["y"]))>1):
            if not any(c["x"]==x and c["y"]==y for c in game["coins"]):
                game["coins"].append({"x":x,"y":y})

def spawn_enemies(n):
    game["enemies"].clear()
    for i in range(n):
        for _ in range(400):
            x = random.randrange(1, GRID_W-1); y = random.randrange(1, GRID_H-1)
            if grid[y][x]==0 and (abs(x-int(game["player"]["x"]))>3 or abs(y-int(game["player"]["y"]))>3):
                ent = {
                    "id": i+1,
                    "x": float(x),
                    "y": float(y),
                    "state": "patrol",
                    "path": [],
                    "last_replan": 0.0,
                    "last_seen": None,
                    "patrol_target": None
                }
                game["enemies"].append(ent)
                break

def reset_all():
    global game
    game = make_game_state()
    spawn_coins(MISSION_COINS)
    spawn_enemies(ENEMY_COUNT)
    game["score"] = 0
    game["mission"]["time_left"] = MISSION_TIME
    game["mission"]["running"] = True
    game["game_over"] = False

# initialize
reset_all()

# === WEBSOCKET MANAGER ===
class ConnectionManager:
    def __init__(self): self.connections = []
    async def connect(self, ws: WebSocket):
        await ws.accept(); self.connections.append(ws)
    def disconnect(self, ws: WebSocket):
        if ws in self.connections: self.connections.remove(ws)
    async def broadcast(self, msg: dict):
        data = json.dumps(msg)
        for ws in list(self.connections):
            try:
                await ws.send_text(data)
            except:
                self.disconnect(ws)

manager = ConnectionManager()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_text(json.dumps({"type":"init","grid":grid,"state":game}))
        while True:
            text = await ws.receive_text()
            try:
                msg = json.loads(text)
                if msg.get("type")=="input":
                    if game.get("game_over"): continue
                    dx = int(msg.get("dx",0)); dy = int(msg.get("dy",0))
                    if dx!=0 and dy!=0:
                        norm = math.sqrt(2)/2
                        dx *= norm; dy *= norm
                    game["player"]["vx"] = dx * PLAYER_SPEED
                    game["player"]["vy"] = dy * PLAYER_SPEED
                elif msg.get("type") == "reset":
                    # reset player only
                    game["player"]["x"] = 2.5; game["player"]["y"]=2.5
                    game["player"]["vx"] = 0.0; game["player"]["vy"] = 0.0
                elif msg.get("type") == "reset_all":
                    reset_all()
            except Exception as e:
                print("bad msg:", e)
    except WebSocketDisconnect:
        manager.disconnect(ws)

# === GAME LOOP: continuous tracking behavior ===
async def game_loop():
    t = 0.0
    while True:
        dt = TICK_DT
        t += dt

        # if game over, do not update positions (pause) but still broadcast state so client shows popup
        if not game.get("game_over"):
            # player movement
            px = game["player"]["x"]; py = game["player"]["y"]
            vx = game["player"]["vx"]; vy = game["player"]["vy"]
            nx = px + vx * dt; ny = py + vy * dt
            def can_at(xf,yf):
                xi, yi = int(round(xf)), int(round(yf))
                return in_bounds(xi,yi) and grid[yi][xi]==0
            if can_at(nx, py): game["player"]["x"]=nx
            if can_at(game["player"]["x"], ny): game["player"]["y"]=ny

            player_tile = (int(round(game["player"]["x"])), int(round(game["player"]["y"])))
            player_vel = (game["player"]["vx"], game["player"]["vy"])

            # enemies ALWAYS track player (no distance/LOS limit)
            for e in game["enemies"]:
                exf, eyf = e["x"], e["y"]
                e_tile = (int(round(exf)), int(round(eyf)))
                # record last_seen always (continuous tracking)
                e["last_seen"] = player_tile
                e["state"] = "chase"

                # Replanning to current/predicted player pos periodically
                if t - e["last_replan"] > REPLAN_INTERVAL:
                    lead_time = 0.25  # small prediction lead
                    target_x = int(round(game["player"]["x"] + player_vel[0]*lead_time))
                    target_y = int(round(game["player"]["y"] + player_vel[1]*lead_time))
                    target_tile = (max(1,min(GRID_W-2,target_x)), max(1,min(GRID_H-2,target_y)))
                    path = astar(e_tile, target_tile)
                    if path:
                        e["path"] = path
                    e["last_replan"] = t

                # follow path
                if e["path"] and len(e["path"])>0:
                    idx = 1 if len(e["path"])>1 else 0
                    nx_tile = e["path"][idx]
                    target_cx = nx_tile[0] + 0.5
                    target_cy = nx_tile[1] + 0.5
                    dirx = target_cx - exf
                    diry = target_cy - eyf
                    dist = math.hypot(dirx,diry) or 1e-6
                    step = ENEMY_SPEED * dt
                    mx = (dirx/dist) * min(step, dist)
                    my = (diry/dist) * min(step, dist)
                    candx = exf + mx
                    candy = eyf + my
                    if in_bounds(int(round(candx)), int(round(candy))) and grid[int(round(candy))][int(round(candx))]==0:
                        e["x"] = candx; e["y"] = candy
                    if abs(e["x"] - (nx_tile[0]+0.5)) < 0.35 and abs(e["y"] - (nx_tile[1]+0.5)) < 0.35:
                        if len(e["path"])>1:
                            e["path"].pop(0)
                else:
                    e["x"] += (random.random()-0.5)*0.02
                    e["y"] += (random.random()-0.5)*0.02

                # collision -> caught
                if int(round(e["x"])) == int(round(game["player"]["x"])) and int(round(e["y"])) == int(round(game["player"]["y"])):
                    # set game over
                    game["game_over"] = True
                    game["mission"]["running"] = False
                    # keep the server state and break out of enemy loop
                    break

            # coins & mission
            pxi, pyi = int(round(game["player"]["x"])), int(round(game["player"]["y"]))
            for c in list(game["coins"]):
                if c["x"]==pxi and c["y"]==pyi:
                    game["coins"].remove(c)
                    game["score"] += 1
                    game["mission"]["coins_collected"] += 1
            if game["mission"]["running"]:
                game["mission"]["time_left"] = max(0, game["mission"]["time_left"] - dt)
                if game["mission"]["coins_collected"] >= game["mission"]["coins_needed"]:
                    game["mission"]["running"] = False
                elif game["mission"]["time_left"] <= 0:
                    game["mission"]["running"] = False

        # broadcast snapshot every tick (even if game_over)
        snapshot = {
            "type":"state",
            "tick": time.time(),
            "state": {
                "player": game["player"],
                "enemies": [
                    {
                        "id": e["id"],
                        "x": e["x"],
                        "y": e["y"],
                        "state": e["state"],
                        "path": e["path"][:12],
                        "last_seen": e.get("last_seen")
                    } for e in game["enemies"]
                ],
                "coins": game["coins"],
                "score": game["score"],
                "mission": game["mission"],
                "game_over": game.get("game_over", False)
            }
        }
        await manager.broadcast(snapshot)
        await asyncio.sleep(TICK_DT)

@app.on_event("startup")
async def start_loop():
    asyncio.create_task(game_loop())

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
