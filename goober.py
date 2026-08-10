import discord, random, re, json, os, time, asyncio, threading, itertools, urllib.parse, io
from discord.ext import commands
from flask import Flask, request, render_template_string, session, redirect, Response, jsonify
from dotenv import load_dotenv

try: from PIL import Image, ImageDraw, ImageFont; image_libs = True
except ImportError: image_libs = False

try: import psutil
except ImportError: psutil = None

load_dotenv()
bot = commands.Bot(command_prefix="!", intents=discord.Intents(message_content=True, guilds=True, messages=True, reactions=True))

MEM_F, SET_F, START_TIME = "goober_memory.json", "goober_settings.json", time.time()
words, emojis, media, server_mem, server_set, user_stats = set(), set(), set(), {}, {}, {}
statuses = ["Learning 🧠", "Goobering 🤪", "Imagining 🎨", "Meming 🖼️"]
status_cycle = itertools.cycle(statuses)

for f, target in [(MEM_F, lambda d: (words.update(d.get("words",[])), emojis.update(d.get("emojis",[])), media.update(d.get("media",[])), server_mem.update(d.get("server_memories",{})), user_stats.update(d.get("user_stats",{})))), (SET_F, lambda d: (server_set.update(d), statuses.clear(), statuses.extend(d.get("custom_statuses", statuses))))]:
    try: target(json.load(open(f))) if os.path.exists(f) else None
    except Exception: pass

def update_status_cycle():
    global status_cycle
    if statuses: status_cycle = itertools.cycle(statuses)
update_status_cycle()

def save():
    try:
        json.dump({"words":list(words),"emojis":list(emojis),"media":list(media),"user_stats":user_stats, "server_memories":{g:{"words":list(m.get("words",[])),"emojis":list(m.get("emojis",[])),"media":list(m.get("media",[]))} for g,m in server_mem.items()}}, open(MEM_F,"w"))
        server_set["custom_statuses"] = statuses; json.dump(server_set, open(SET_F,"w"))
    except Exception: pass

def get_set(g):
    return server_set.setdefault(str(g), {"words":True,"emojis":True,"media":True,"words_scope":"global","emojis_scope":"global","media_scope":"global","response_chance":100,"meme_channel":None})

def get_mem(g):
    sm = server_mem.setdefault(str(g), {"words":[],"emojis":[],"media":[]})
    return {"words":set(sm["words"]), "emojis":set(sm["emojis"]), "media":set(sm["media"])}

def get_sys_metrics():
    if psutil:
        try: return int(psutil.cpu_percent()), int(psutil.virtual_memory().percent)
        except Exception: pass
    try: return min(100, int((os.getloadavg()[0] / (os.cpu_count() or 1)) * 100)), 0
    except Exception: return 0, 0

def draw_txt(d, t, y, w, f):
    for ox, oy in [(-2,-2),(2,-2),(-2,2),(2,2),(-2,0),(2,0),(0,-2),(0,2)]: d.text((((w-d.textlength(t,f))//2)+ox, y+oy), t, font=f, fill='black')
    d.text(((w-d.textlength(t,f))//2, y), t, font=f, fill='white')

def get_pool(scope, cat_name, gid, global_set):
    if scope == "global": return list(global_set)
    if scope == "local": return list(get_mem(gid)[cat_name])
    return list(get_mem(scope)[cat_name])

@bot.event
async def on_ready():
    print(f"Online as: {bot.user.name}")
    async def rot():
        while not bot.is_closed():
            if statuses: await bot.change_presence(activity=discord.Game(next(status_cycle)))
            await asyncio.sleep(60)
    bot.loop.create_task(rot())

@bot.event
async def on_message(msg):
    if msg.author == bot.user or not msg.guild: return
    gid, up = str(msg.guild.id), False
    st, sm = get_set(gid), get_mem(gid)

    if not msg.content.startswith("!"):
        if st.get("media"):
            urls = [a.url for a in msg.attachments if a.content_type and any(x in a.content_type for x in ['image','gif'])] + [w for w in msg.content.split() if re.match(r'https?://\S+', w) and any(x in w.lower() for x in ['.gif','.png','.jpg','.jpeg','.webp','tenor.com'])]
            for u in urls:
                if u not in media: media.add(u); sm["media"].add(u); up = True
        if st.get("emojis"):
            for e in set(re.findall(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', msg.content)) - emojis:
                emojis.add(e); sm["emojis"].add(e); up = True
        if st.get("words"):
            for cw in [w.strip(".,!?\"'()[]{}").lower() for w in msg.content.split() if not re.match(r'https?://\S+|<a?:[a-zA-Z0-9_]+:[0-9]+>', w)]:
                if len(cw) > 1 and cw not in words: words.add(cw); sm["words"].add(cw); up = True

    trig = bot.user in msg.mentions or "goober" in msg.content.lower() or (msg.reference and msg.reference.resolved and msg.reference.resolved.author == bot.user)
    if trig:
        uid = str(msg.author.id)
        user_stats.setdefault(uid, {"count":0, "name":""}); user_stats[uid]["count"] += 1; user_stats[uid]["name"] = msg.author.display_name; up = True

    if up: server_mem[gid] = {"words":list(sm["words"]),"emojis":list(sm["emojis"]),"media":list(sm["media"])}; save()

    if trig and random.randint(1, 100) <= st.get("response_chance", 100):
        w_pool = get_pool(st.get("words_scope", "global"), "words", gid, words)
        e_pool = get_pool(st.get("emojis_scope", "global"), "emojis", gid, emojis)
        m_pool = get_pool(st.get("media_scope", "global"), "media", gid, media)
        pool = w_pool + e_pool + m_pool
        await msg.channel.send(" ".join(random.sample(pool, random.randint(1, min(5, len(pool))))) if pool else "goober")

    if random.randint(1, 100) == 1:
        r_pool = get_pool(st.get("emojis_scope", "global"), "emojis", gid, emojis)
        try: await msg.add_reaction(random.choice(r_pool + ["👍","😂","💀","🔥","😎","💩","👀"]))
        except discord.HTTPException: pass
    await bot.process_commands(msg)

@bot.command()
async def goob(ctx, *, prompt: str):
    await (msg := await ctx.send(f"🎨 Imagining: `{prompt}`...")).delete()
    await ctx.send(embed=discord.Embed(title=f"🎨 Goober Created: {prompt}", color=0x3498db).set_image(url=f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}").set_footer(text=f"Requested by {ctx.author.name}"))

@bot.command()
async def meme(ctx, *, txt: str):
    if not image_libs: return await ctx.send("❌ Error: Pillow missing.")
    st, sm = get_set(str(ctx.guild.id)), get_mem(str(ctx.guild.id))
    if st.get("meme_channel") and ctx.channel.id != st["meme_channel"]: return await ctx.send(f"⚠️ Use <#{st['meme_channel']}>.", delete_after=10)
    
    pool = get_pool(st.get("media_scope", "global"), "media", str(ctx.guild.id), media)
    if not pool: return await ctx.send("❌ Error: No media learned in this scope.")
    url = random.choice(pool)
    if any(x in url for x in ["tenor.com","giphy.com"]): return await ctx.send("❌ Randomly pulled a GIF. Try again.", delete_after=10)
    
    await ctx.send("👨‍🍳 Cooking meme...", delete_after=5)
    parts = txt.split('|', 1); t_t, b_t = parts[0].strip().upper(), parts[1].strip().upper() if len(parts)>1 else ""
    
    import requests
    try: img = Image.open(io.BytesIO(requests.get(url, timeout=10).content)).convert("RGBA")
    except Exception: return await ctx.send("❌ Download failed.")
    
    d, (w, h) = ImageDraw.Draw(img), img.size
    try: f = ImageFont.truetype("arial.ttf", size=int(h/12))
    except Exception: f = ImageFont.load_default()
    
    if t_t: draw_txt(d, t_t, 10, w, f)
    if b_t: draw_txt(d, b_t, h - int(h/10) - 10, w, f)
    
    out = io.BytesIO(); img.convert("RGB").save(out, 'PNG'); out.seek(0)
    await ctx.send(file=discord.File(fp=out, filename="m.png"), embed=discord.Embed(color=0x2ecc71).set_image(url="attachment://m.png").set_footer(text=f"Meme by {ctx.author.name}"))

@bot.command()
@commands.has_permissions(administrator=True)
async def set_meme_channel(ctx, c: discord.TextChannel = None):
    get_set(str(ctx.guild.id))["meme_channel"] = c.id if c else None; save()
    await ctx.send(f"✅ Memes restricted to {c.mention}." if c else "✅ Meme restriction removed.")

@bot.command()
@commands.has_permissions(administrator=True)
async def wipe_memory(ctx):
    words.clear(); emojis.clear(); media.clear(); server_mem.clear(); user_stats.clear(); save()
    await ctx.send("🧹 Brain wiped!")

@bot.command()
@commands.has_permissions(administrator=True)
async def clear_mem(ctx, category: str):
    category = category.lower()
    if category not in ["words", "emojis", "media"]:
        return await ctx.send("❌ Category must be `words`, `emojis`, or `media`.")
    sm = get_mem(str(ctx.guild.id))
    sm[category].clear()
    server_mem[str(ctx.guild.id)] = {k: list(v) for k, v in sm.items()}
    save()
    await ctx.send(f"🧹 Cleared all {category} from this server's memory banks!")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret123")

HTML = """<!DOCTYPE html><html><head><title>Goober Suite Control Center</title><meta name="viewport" content="width=device-width, initial-scale=1">
<style>:root{--bg:#0f111a;--card:#1e2233;--a:#89b4fa;--r:#f38ba8;--g:#a6e3a1;--o:#fab387;--t:#cdd6f4}
body{font-family:'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--t);padding:20px;margin:0;box-sizing:border-box}
*,*:before,*:after{box-sizing:inherit}
.header-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;border-bottom:1px solid #2e344d;padding-bottom:12px}
.header-bar h2{margin:0;font-size:22px;letter-spacing:0.5px}
.card{background:var(--card);padding:18px;border-radius:12px;margin-bottom:16px;border:1px solid #2e344d;box-shadow:0 4px 16px rgba(0,0,0,0.2)}
.card h3{margin-top:0;font-size:16px;margin-bottom:14px;color:var(--a);border-bottom:1px solid #2e344d;padding-bottom:8px}
.btn{padding:8px 14px;border:none;border-radius:6px;cursor:pointer;font-weight:600;font-size:12px;display:inline-flex;align-items:center;justify-content:center;transition:opacity 0.2s}
.btn:hover{opacity:0.85}
input,select,textarea{width:100%;padding:10px;background:#121420;color:#fff;border:1px solid #2e344d;margin-bottom:12px;border-radius:6px;font-size:13px}
.chip{background:#282d42;padding:5px 10px;border-radius:14px;display:inline-flex;align-items:center;gap:6px;margin:3px;font-size:12px}
.row{display:flex;justify-content:space-between;align-items:center;background:#141724;padding:12px;margin-bottom:8px;border-radius:8px;flex-wrap:wrap;gap:10px}
.nav{display:flex;gap:8px;margin-bottom:20px;overflow-x:auto;padding-bottom:4px}
.tb{background:var(--card);color:#9399b2;border:1px solid #2e344d;padding:10px 18px;border-radius:8px;cursor:pointer;font-weight:600;font-size:13px;white-space:nowrap;transition:all 0.2s}
.tb.act{background:var(--a);color:#111;border-color:var(--a);font-weight:bold}
.tc{display:none}.tc.act{display:block}
.pg{background:#121420;border-radius:10px;height:14px;border:1px solid #2e344d;margin-top:6px;margin-bottom:12px;overflow:hidden}
.pf{background:var(--a);height:100%;width:0%;transition:width .4s ease}
.grid-form{display:grid;grid-template-columns:1fr auto auto;gap:8px;align-items:center}
.server-controls{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
select.scope-select {background:var(--o); color:#111; padding:6px; width:auto; margin:0; border:none; font-weight:bold; cursor:pointer;}
</style>
<script>
function T(n,b){document.querySelectorAll('.tc').forEach(x=>x.classList.remove('act'));document.querySelectorAll('.tb').forEach(x=>x.classList.remove('act'));document.getElementById(n).classList.add('act');b.classList.add('act');localStorage.setItem('gT',n)}
document.addEventListener("DOMContentLoaded",()=>{let s=localStorage.getItem('gT')||'d';let btn=document.querySelector(`[data-t="${s}"]`)||document.querySelector('.tb');if(btn)T(s,btn)});
async function A(u,b={}){let r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});if((await r.json()).ok)location.reload()}
new EventSource("/stream").onmessage=e=>{let d=JSON.parse(e.data);document.getElementById("u").innerText=d.u;document.getElementById("cp").style.width=d.c+'%';document.getElementById("rm").style.width=d.r+'%';};
</script></head><body>
<div class="header-bar">
    <h2>🤖 Goober Suite Control Center</h2>
    <a href="/logout" class="btn" style="background:var(--r);color:#111;text-decoration:none">Logout Session</a>
</div>
<div class="nav">
    <button class="tb act" data-t="d" onclick="T('d',this)">📊 System Dashboard</button>
    <button class="tb" data-t="r" onclick="T('r',this)">🏆 Leaderboard Ranks</button>
    <button class="tb" data-t="b" onclick="T('b',this)">📢 Broadcast Message</button>
    <button class="tb" data-t="s" onclick="T('s',this)">🌐 Servers & Scopes</button>
    <button class="tb" data-t="m" onclick="T('m',this)">🧠 Memory Manager</button>
</div>

<div id="d" class="tc act">
    <div class="card">
        <h3>System Health Monitor</h3>
        <div style="margin-bottom:10px"><b>Uptime:</b> <span id="u" style="color:var(--g)">...</span></div>
        <div>CPU Usage</div><div class="pg"><div id="cp" class="pf"></div></div>
        <div>RAM Usage</div><div class="pg"><div id="rm" class="pf" style="background:var(--g)"></div></div>
    </div>
    <div class="card">
        <h3>Custom Statuses</h3>
        <div class="grid-form">
            <input type="text" id="ns" placeholder="Enter status text..." style="margin:0">
            <button class="btn" onclick="A('/add_status',{status:document.getElementById('ns').value})" style="background:var(--a);color:#111">Add Status</button>
        </div>
        <div style="margin-top:12px">
            {% for s in status_list %}
                <span class="chip">{{s}} <button class="btn" onclick="A('/del_status',{idx:{{loop.index0}}})" style="background:var(--r);padding:2px 6px;font-size:10px;color:#fff">✕</button></span>
            {% endfor %}
        </div>
    </div>
    <div class="card">
        <h3>Danger Zone Controls</h3>
        <div style="display:flex;gap:10px">
            <form action="/power" method="post" style="display:inline"><button class="btn" style="background:var(--r);color:#111">Power Off Bot</button></form>
            <form action="/wipe" method="post" style="display:inline"><button class="btn" style="background:var(--o);color:#111" onclick="return confirm('Wipe all server data and memories?')">Wipe All Memory</button></form>
        </div>
    </div>
</div>

<div id="r" class="tc">
    <div class="card">
        <h3>Leaderboard Ranks</h3>
        {% for u in leaderboard %}
            <div class="row">
                <span><b>#{{loop.index}}</b> {{u.name}}</span>
                <span class="chip" style="background:var(--a);color:#111;font-weight:bold">{{u.count}} interactions</span>
            </div>
        {% else %}
            <p style="color:#9399b2;font-size:13px;margin:0">No interactions recorded yet. Mention or interact with Goober in Discord to populate ranks!</p>
        {% endfor %}
    </div>
</div>

<div id="b" class="tc">
    <div class="card">
        <h3>Broadcast Message</h3>
        <form action="/send" method="post" enctype="multipart/form-data">
            <label style="font-size:12px;color:#9399b2">Target Channel</label>
            <select name="cid">
                {% for c in channels %}
                    <option value="{{c.id}}">{{c.guild}} ➔ #{{c.name}}</option>
                {% endfor %}
            </select>
            <label style="font-size:12px;color:#9399b2">Message Text</label>
            <textarea name="txt" rows="3" placeholder="Type your broadcast message..."></textarea>
            <label style="font-size:12px;color:#9399b2">Optional File / Attachment</label>
            <input type="file" name="file" style="margin-bottom:14px">
            <button class="btn" style="background:var(--a);color:#111;width:100%;padding:10px">Send Message to Discord</button>
        </form>
    </div>
</div>

<div id="s" class="tc">
    <div class="card">
        <h3>Servers and Scopes (Cross-Server Linking)</h3>
        {% for g in guilds %}
            <div class="row">
                <div style="font-weight:600">{{g.name}}</div>
                <div class="server-controls">
                    <input type="number" id="ch-{{g.id}}" value="{{g.st.response_chance}}" min="1" max="100" style="width:60px;margin:0;padding:6px" title="Response Chance %">
                    <button class="btn" onclick="A('/set_chance',{gid:'{{g.id}}',ch:document.getElementById('ch-{{g.id}}').value})" style="background:var(--a);color:#111">Save %</button>
                    
                    <select class="scope-select" onchange="A('/set_scope',{gid:'{{g.id}}',cat:'words_scope',val:this.value})">
                        <option value="global" {% if g.st.words_scope == 'global' %}selected{% endif %}>Words: Global</option>
                        <option value="local" {% if g.st.words_scope == 'local' %}selected{% endif %}>Words: Local</option>
                        {% for og in guilds %}{% if og.id != g.id %}<option value="{{og.id}}" {% if g.st.words_scope == og.id %}selected{% endif %}>Words: {{og.name}}</option>{% endif %}{% endfor %}
                    </select>

                    <select class="scope-select" onchange="A('/set_scope',{gid:'{{g.id}}',cat:'emojis_scope',val:this.value})">
                        <option value="global" {% if g.st.emojis_scope == 'global' %}selected{% endif %}>Emojis: Global</option>
                        <option value="local" {% if g.st.emojis_scope == 'local' %}selected{% endif %}>Emojis: Local</option>
                        {% for og in guilds %}{% if og.id != g.id %}<option value="{{og.id}}" {% if g.st.emojis_scope == og.id %}selected{% endif %}>Emojis: {{og.name}}</option>{% endif %}{% endfor %}
                    </select>

                    <select class="scope-select" onchange="A('/set_scope',{gid:'{{g.id}}',cat:'media_scope',val:this.value})">
                        <option value="global" {% if g.st.media_scope == 'global' %}selected{% endif %}>Media: Global</option>
                        <option value="local" {% if g.st.media_scope == 'local' %}selected{% endif %}>Media: Local</option>
                        {% for og in guilds %}{% if og.id != g.id %}<option value="{{og.id}}" {% if g.st.media_scope == og.id %}selected{% endif %}>Media: {{og.name}}</option>{% endif %}{% endfor %}
                    </select>

                    <button class="btn" onclick="A('/toggle',{gid:'{{g.id}}',t:'words'})" style="background:{{'var(--g)' if g.st.words else 'var(--r)'}};color:#111" title="Toggle active learning">Learning</button>
                </div>
            </div>
        {% endfor %}
    </div>
</div>

<div id="m" class="tc">
    <div class="card">
        <h3>🧹 Bulk Clear Server Memory</h3>
        <p style="font-size:12px;color:#9399b2;margin-top:0">Wipe an entire category for a specific server (or the global brain).</p>
        <div class="grid-form">
            <select id="c-tgt" style="margin:0">
                <option value="global">Global Brain</option>
                {% for g in guilds %}
                    <option value="{{g.id}}">{{g.name}}</option>
                {% endfor %}
            </select>
            <select id="c-t" style="margin:0">
                <option value="words">Words</option>
                <option value="emojis">Emojis</option>
                <option value="media">Media URLs</option>
            </select>
            <button class="btn" onclick="if(confirm('Are you sure you want to wipe this entire category?')) A('/clear_category',{type:document.getElementById('c-t').value,gid:document.getElementById('c-tgt').value})" style="background:var(--o);color:#111">Wipe Category</button>
        </div>
    </div>
    
    <div class="card">
        <h3>Memory Injector</h3>
        <div class="grid-form">
            <select id="i-tgt" style="margin:0">
                <option value="global">Global Brain</option>
                {% for g in guilds %}
                    <option value="{{g.id}}">{{g.name}}</option>
                {% endfor %}
            </select>
            <select id="i-t" style="margin:0">
                <option value="word">Word</option>
                <option value="emoji">Emoji</option>
                <option value="media">Media URL</option>
            </select>
            <button class="btn" onclick="A('/inject',{type:document.getElementById('i-t').value,value:document.getElementById('i-v').value,gid:document.getElementById('i-tgt').value})" style="background:var(--g);color:#111">Inject</button>
        </div>
        <input type="text" id="i-v" placeholder="Enter word, emoji or media URL to inject..." style="margin-top:8px;margin-bottom:0">
    </div>
    <div class="card">
        <h3>Learned Words ({{w_cnt}})</h3>
        <div style="max-height:220px;overflow-y:auto;padding-right:4px">
            {% for w in word_list %}
                <span class="chip">{{w}} <button class="btn" onclick="A('/del_item',{type:'word',val:'{{w}}'})" style="background:var(--r);padding:2px 6px;font-size:10px;color:#fff">✕</button></span>
            {% endfor %}
        </div>
    </div>
</div>

</body></html>"""

@app.route("/login", methods=["GET","POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("pwd") == os.getenv("DASHBOARD_PASSWORD","admin"):
            session["auth"] = True
            return redirect("/")
        else:
            error = "Invalid password!"
    return f'<body style="background:#0f111a;color:#fff;text-align:center;padding:50px"><form method="post"><h2>🤖 Goober Login</h2><input type="password" name="pwd" placeholder="Password" style="padding:8px"><br><br><button style="padding:6px 12px">Login</button>{f"<p style=color:red>{error}</p>" if error else ""}</form></body>'

@app.route("/logout")
def logout():
    session.pop("auth", None)
    return redirect("/login")

@app.route("/")
def home():
    if not session.get("auth"): 
        return redirect("/login")
    return render_template_string(HTML, channels=[{"id":c.id,"name":c.name,"guild":g.name} for g in bot.guilds for c in g.text_channels], guilds=[{"id":str(g.id),"name":g.name,"st":get_set(g.id)} for g in bot.guilds], leaderboard=sorted(user_stats.values(), key=lambda x:x["count"], reverse=True)[:10], w_cnt=len(words), word_list=list(words), media_list=list(media), status_list=statuses)

@app.route("/stream")
def stream():
    def gen():
        while True:
            u, (c, r) = int(time.time() - START_TIME), get_sys_metrics()
            yield f"data: {json.dumps({'u':f'{u//3600}h {(u%3600)//60}m {u%60}s','c':c,'r':r})}\n\n"; time.sleep(2)
    return Response(gen(), mimetype="text/event-stream")

@app.route("/<path:action>", methods=["POST"])
def api_route(action):
    if not session.get("auth"): 
        return jsonify({"ok": False})
    
    d = request.get_json(silent=True) or {}
    ok = True
    
    if action == "inject":
        t, v, gid = d.get("type"), d.get("value", "").strip(), d.get("gid", "global")
        if gid != "global":
            sm = get_mem(gid)
            if t == "word" and v: sm["words"].add(v.lower())
            elif t == "emoji" and v: sm["emojis"].add(v)
            elif t == "media" and v: sm["media"].add(v)
            server_mem[gid] = {k: list(v) for k, v in sm.items()}
        else:
            if t == "word" and v: words.add(v.lower())
            elif t == "emoji" and v: emojis.add(v)
            elif t == "media" and v: media.add(v)
            
    elif action == "del_item":
        t, v, gid = d.get("type"), d.get("val"), d.get("gid", "global")
        if gid != "global":
            sm = get_mem(gid)
            if t == "word" and v in sm["words"]: sm["words"].remove(v)
            elif t == "media" and v in sm["media"]: sm["media"].remove(v)
            server_mem[gid] = {k: list(v) for k, v in sm.items()}
        else:
            if t == "word" and v in words: words.remove(v)
            elif t == "media" and v in media: media.remove(v)
            
    elif action == "clear_category":
        t, gid = d.get("type"), d.get("gid", "global")
        if gid != "global":
            sm = get_mem(gid)
            if t in sm: sm[t].clear()
            server_mem[gid] = {k: list(v) for k, v in sm.items()}
        else:
            if t == "words": words.clear()
            elif t == "emojis": emojis.clear()
            elif t == "media": media.clear()
            
    elif action == "add_status":
        st = d.get("status", "").strip()
        if st and st not in statuses: 
            statuses.append(st)
            update_status_cycle()
            
    elif action == "del_status":
        idx = int(d.get("idx", -1))
        if 0 <= idx < len(statuses): 
            statuses.pop(idx)
            update_status_cycle()

    elif action == "set_scope":
        get_set(d.get("gid"))[d.get("cat")] = d.get("val")
            
    elif action == "toggle":
        st, t = get_set(d.get("gid")), d.get("t")
        st[t] = not st.get(t, True)
            
    elif action == "set_chance":
        get_set(d.get("gid"))["response_chance"] = max(1, min(100, int(d.get("ch", 100))))
        
    elif action == "wipe":
        words.clear(); emojis.clear(); media.clear(); server_mem.clear(); user_stats.clear()
        save()
        return redirect("/")
        
    elif action == "power":
        os._exit(0)
        
    elif action == "send":
        txt = request.form.get("txt", "").strip()
        f = request.files.get("file")
        cid = request.form.get("cid")
        c = bot.get_channel(int(cid)) if cid else None
        if c: 
            file_obj = discord.File(f, filename=f.filename) if f and f.filename else None
            asyncio.run_coroutine_threadsafe(c.send(content=txt or None, file=file_obj), bot.loop)
        return redirect("/")
        
    else:
        ok = False
        
    if ok: 
        save()
    return jsonify({"ok": ok})

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000))), daemon=True).start()
    bot.run(os.getenv("DISCORD_TOKEN", ""))