
import asyncio, json, math, heapq, random, time
from typing import List, Tuple
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

GRID_W = 28
GRID_H = 18
TICK_DT = 0.06
REPLAN_INTERVAL = 0.22
ENEMY_SPEED = 2.8        
PLAYER_SPEED = 6.0       
ENEMY_COUNT = 4
MISSION_COINS = 8
MISSION_TIME = 120      


def in_bounds(x,y): return 0 <= x < GRID_W and 0 <= y < GRID_H


grid = [[0 for _ in range(GRID_W)] for _ in range(GRID_H)]
random.seed(2)

for x in range(GRID_W):
    grid[0][x] = grid[GRID_H-1][x] = 1
for y in range(GRID_H):
    grid[y][0] = grid[y][GRID_W-1] = 1

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


reset_all()


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


async def game_loop():
    t = 0.0
    while True:
        dt = TICK_DT
        t += dt

       
        if not game.get("game_over"):
            
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

            
            for e in game["enemies"]:
                exf, eyf = e["x"], e["y"]
                e_tile = (int(round(exf)), int(round(eyf)))
                e["last_seen"] = player_tile
                e["state"] = "chase"

                
                if t - e["last_replan"] > REPLAN_INTERVAL:
                    lead_time = 0.25  
                    target_x = int(round(game["player"]["x"] + player_vel[0]*lead_time))
                    target_y = int(round(game["player"]["y"] + player_vel[1]*lead_time))
                    target_tile = (max(1,min(GRID_W-2,target_x)), max(1,min(GRID_H-2,target_y)))
                    path = astar(e_tile, target_tile)
                    if path:
                        e["path"] = path
                    e["last_replan"] = t

               
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

              
                if int(round(e["x"])) == int(round(game["player"]["x"])) and int(round(e["y"])) == int(round(game["player"]["y"])):
                   
                    game["game_over"] = True
                    game["mission"]["running"] = False
                
                    break

         
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
