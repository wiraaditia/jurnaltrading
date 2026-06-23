import os
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

# Local imports
from database import engine, Base, get_db
import models
from services.storage import save_image
from services.backtest import calculate_backtest_stats

# Create SQLite tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cryptonicle - Crypto Futures Trading Journal")

# Mount uploads folder to serve uploaded chart images
if os.environ.get("VERCEL"):
    UPLOAD_DIR = "/tmp/uploads"
else:
    UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Jinja2 Templates Setup
templates = Jinja2Templates(directory="templates")

# Helper function to compute journal stats
def get_journal_stats(db: Session):
    entries = db.query(models.JournalEntry).all()
    total_trades = len(entries)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0,
            "total_pnl": 0.0,
            "active_trades": 0
        }
    
    wins = sum(1 for e in entries if e.status.lower() == "win")
    losses = sum(1 for e in entries if e.status.lower() == "loss")
    active_trades = sum(1 for e in entries if e.status.lower() == "running")
    
    # Winrate based on completed trades (win / loss)
    completed_trades = wins + losses
    winrate = round((wins / completed_trades) * 100, 2) if completed_trades > 0 else 0.0
    
    total_pnl = sum(e.pnl for e in entries if e.pnl is not None)
    
    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "total_pnl": round(total_pnl, 2),
        "active_trades": active_trades
    }

@app.get("/", response_class=HTMLResponse)
def read_journal(request: Request, db: Session = Depends(get_db)):
    entries = db.query(models.JournalEntry).order_by(models.JournalEntry.created_at.desc()).all()
    stats = get_journal_stats(db)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"entries": entries, "stats": stats, "active_page": "journal"}
    )

@app.post("/journal", response_class=HTMLResponse)
async def create_journal_entry(
    request: Request,
    pair: str = Form(...),
    position_type: str = Form(...),
    leverage: int = Form(10),
    entry_price: float = Form(...),
    tp_price: Optional[float] = Form(None),
    sl_price: Optional[float] = Form(None),
    status: str = Form("Running"),
    pnl: Optional[float] = Form(0.0),
    notes: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    # Handle image upload using storage service
    image_url = ""
    if image and image.filename:
        image_url = save_image(image)

    # Save journal entry to database
    entry = models.JournalEntry(
        pair=pair.upper(),
        position_type=position_type,
        leverage=leverage,
        entry_price=entry_price,
        tp_price=tp_price,
        sl_price=sl_price,
        status=status,
        pnl=pnl or 0.0,
        notes=notes,
        image_url=image_url
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # Recalculate stats
    stats = get_journal_stats(db)

    # Render card item & include updated stats card OOB (out of band)
    card_html = templates.TemplateResponse(
        request=request,
        name="components/card_item.html",
        context={"entry": entry}
    ).body.decode("utf-8")
    
    stats_html = templates.TemplateResponse(
        request=request,
        name="components/card.html",
        context={"stats": stats}
    ).body.decode("utf-8")

    # Combine both responses (card goes to container, stats swaps OOB)
    return HTMLResponse(content=card_html + stats_html)

@app.delete("/journal/{entry_id}", response_class=HTMLResponse)
def delete_journal_entry(request: Request, entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    
    # Optional: Delete local image file if exists
    if entry.image_url and entry.image_url.startswith("/uploads/"):
        filename = entry.image_url.split("/")[-1]
        local_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception as e:
                print(f"Failed to delete local file: {e}")

    db.delete(entry)
    db.commit()

    # Recalculate stats and return OOB update
    stats = get_journal_stats(db)
    stats_html = templates.TemplateResponse(
        request=request,
        name="components/card.html",
        context={"stats": stats}
    ).body.decode("utf-8")

    # Returns empty body for the deleted element (hx-target targets the deleted card itself)
    # and includes the OOB updated stats card
    return HTMLResponse(content=stats_html)

@app.get("/journal/{entry_id}", response_class=HTMLResponse)
def get_journal_entry(request: Request, entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return templates.TemplateResponse(
        request=request,
        name="components/card_item.html",
        context={"entry": entry}
    )

@app.get("/journal/{entry_id}/edit", response_class=HTMLResponse)
def edit_journal_entry(request: Request, entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return templates.TemplateResponse(
        request=request,
        name="components/card_edit.html",
        context={"entry": entry}
    )

@app.post("/journal/{entry_id}", response_class=HTMLResponse)
async def update_journal_entry(
    request: Request,
    entry_id: int,
    pair: str = Form(...),
    position_type: str = Form(...),
    leverage: int = Form(10),
    entry_price: float = Form(...),
    tp_price: Optional[float] = Form(None),
    sl_price: Optional[float] = Form(None),
    status: str = Form("Running"),
    pnl: Optional[float] = Form(0.0),
    notes: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    entry = db.query(models.JournalEntry).filter(models.JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    # Update basic fields
    entry.pair = pair.upper()
    entry.position_type = position_type
    entry.leverage = leverage
    entry.entry_price = entry_price
    entry.tp_price = tp_price
    entry.sl_price = sl_price
    entry.status = status
    entry.pnl = pnl or 0.0
    entry.notes = notes

    # Handle image upload if a new file is uploaded
    if image and image.filename:
        # Delete old image if it existed
        if entry.image_url and entry.image_url.startswith("/uploads/"):
            old_filename = entry.image_url.split("/")[-1]
            old_path = os.path.join(UPLOAD_DIR, old_filename)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception as e:
                    print(f"Failed to delete old file: {e}")
        
        # Save new image
        entry.image_url = save_image(image)

    db.commit()
    db.refresh(entry)

    # Recalculate stats
    stats = get_journal_stats(db)

    # Render card item & include updated stats card OOB
    card_html = templates.TemplateResponse(
        request=request,
        name="components/card_item.html",
        context={"entry": entry}
    ).body.decode("utf-8")
    
    stats_html = templates.TemplateResponse(
        request=request,
        name="components/card.html",
        context={"stats": stats}
    ).body.decode("utf-8")

    return HTMLResponse(content=card_html + stats_html)

@app.get("/backtest", response_class=HTMLResponse)
def read_backtest(request: Request, db: Session = Depends(get_db)):
    trades = db.query(models.BacktestTrade).order_by(models.BacktestTrade.created_at.desc()).all()
    stats = calculate_backtest_stats(trades)
    return templates.TemplateResponse(
        request=request,
        name="backtest.html",
        context={"trades": trades, "stats": stats, "active_page": "backtest"}
    )

@app.post("/backtest", response_class=HTMLResponse)
def create_backtest_entry(
    request: Request,
    pair: str = Form(...),
    position_type: str = Form(...),
    entry_price: float = Form(...),
    exit_price: float = Form(...),
    status: str = Form(...),
    pnl: float = Form(...),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    trade = models.BacktestTrade(
        pair=pair.upper(),
        position_type=position_type,
        entry_price=entry_price,
        exit_price=exit_price,
        status=status,
        pnl=pnl,
        notes=notes
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)

    trades = db.query(models.BacktestTrade).all()
    stats = calculate_backtest_stats(trades)

    row_html = templates.TemplateResponse(
        request=request,
        name="components/backtest_row.html",
        context={"trade": trade}
    ).body.decode("utf-8")

    stats_html = templates.TemplateResponse(
        request=request,
        name="backtest.html",
        context={"stats": stats}
    ).body.decode("utf-8")
    
    # Extract just the stats container from backtest.html or update manually
    # Let's construct the stats OOB block
    oob_stats_html = f"""
    <div id="backtest-stats" class="grid grid-cols-1 md:grid-cols-4 gap-4" hx-swap-oob="true">
        <div class="bg-brand-card border border-brand-accent/50 rounded-2xl p-5 flex flex-col justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-gray-500">Backtest Trades</span>
            <div class="flex items-baseline justify-between mt-4">
                <span class="text-3xl font-mono font-bold text-white">{stats['total_trades']}</span>
                <span class="text-xs px-2.5 py-1 rounded-full bg-brand-accent text-gray-400 font-medium">Trades</span>
            </div>
        </div>
        <div class="bg-brand-card border border-brand-accent/50 rounded-2xl p-5 flex flex-col justify-between {'glow-success/10' if stats['winrate'] >= 50 else 'glow-danger/10'}">
            <span class="text-xs font-semibold uppercase tracking-wider text-gray-500">Simulated Win Rate</span>
            <div class="flex items-baseline justify-between mt-4">
                <span class="text-3xl font-mono font-bold {'text-brand-success' if stats['winrate'] >= 50 else 'text-brand-danger'}">
                    {stats['winrate']}%
                </span>
                <span class="text-xs px-2.5 py-1 rounded-full font-medium {'bg-brand-success/10 text-brand-success' if stats['winrate'] >= 50 else 'bg-brand-danger/10 text-brand-danger'}">
                    {stats['wins']}W - {stats['losses']}L
                </span>
            </div>
        </div>
        <div class="bg-brand-card border border-brand-accent/50 rounded-2xl p-5 flex flex-col justify-between {'glow-success/10' if stats['total_pnl'] >= 0 else 'glow-danger/10'}">
            <span class="text-xs font-semibold uppercase tracking-wider text-gray-500">Simulated Net Profit</span>
            <div class="flex items-baseline justify-between mt-4">
                <span class="text-3xl font-mono font-bold {'text-brand-success' if stats['total_pnl'] >= 0 else 'text-brand-danger'}">
                    {'+' if stats['total_pnl'] > 0 else ''}{stats['total_pnl']}%
                </span>
                <span class="text-xs px-2.5 py-1 rounded-full bg-brand-accent/50 text-gray-400 font-medium font-mono">
                    Total
                </span>
            </div>
        </div>
        <div class="bg-brand-card border border-brand-accent/50 rounded-2xl p-5 flex flex-col justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-gray-500">Avg Profit/Loss per Trade</span>
            <div class="flex items-baseline justify-between mt-4">
                <span class="text-3xl font-mono font-bold {'text-brand-success' if stats['avg_pnl'] >= 0 else 'text-brand-danger'}">
                    {'+' if stats['avg_pnl'] > 0 else ''}{stats['avg_pnl']}%
                </span>
                <span class="text-xs px-2.5 py-1 rounded-full bg-brand-accent/50 text-gray-400 font-medium font-mono">
                    Average
                </span>
            </div>
        </div>
    </div>
    """

    return HTMLResponse(content=row_html + oob_stats_html)

@app.delete("/backtest/{trade_id}", response_class=HTMLResponse)
def delete_backtest_entry(request: Request, trade_id: int, db: Session = Depends(get_db)):
    trade = db.query(models.BacktestTrade).filter(models.BacktestTrade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Backtest trade not found")
    
    db.delete(trade)
    db.commit()

    trades = db.query(models.BacktestTrade).all()
    stats = calculate_backtest_stats(trades)

    # Return OOB update of stats card, empty response for target row removal
    oob_stats_html = f"""
    <div id="backtest-stats" class="grid grid-cols-1 md:grid-cols-4 gap-4" hx-swap-oob="true">
        <div class="bg-brand-card border border-brand-accent/50 rounded-2xl p-5 flex flex-col justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-gray-500">Backtest Trades</span>
            <div class="flex items-baseline justify-between mt-4">
                <span class="text-3xl font-mono font-bold text-white">{stats['total_trades']}</span>
                <span class="text-xs px-2.5 py-1 rounded-full bg-brand-accent text-gray-400 font-medium">Trades</span>
            </div>
        </div>
        <div class="bg-brand-card border border-brand-accent/50 rounded-2xl p-5 flex flex-col justify-between {'glow-success/10' if stats['winrate'] >= 50 else 'glow-danger/10'}">
            <span class="text-xs font-semibold uppercase tracking-wider text-gray-500">Simulated Win Rate</span>
            <div class="flex items-baseline justify-between mt-4">
                <span class="text-3xl font-mono font-bold {'text-brand-success' if stats['winrate'] >= 50 else 'text-brand-danger'}">
                    {stats['winrate']}%
                </span>
                <span class="text-xs px-2.5 py-1 rounded-full font-medium {'bg-brand-success/10 text-brand-success' if stats['winrate'] >= 50 else 'bg-brand-danger/10 text-brand-danger'}">
                    {stats['wins']}W - {stats['losses']}L
                </span>
            </div>
        </div>
        <div class="bg-brand-card border border-brand-accent/50 rounded-2xl p-5 flex flex-col justify-between {'glow-success/10' if stats['total_pnl'] >= 0 else 'glow-danger/10'}">
            <span class="text-xs font-semibold uppercase tracking-wider text-gray-500">Simulated Net Profit</span>
            <div class="flex items-baseline justify-between mt-4">
                <span class="text-3xl font-mono font-bold {'text-brand-success' if stats['total_pnl'] >= 0 else 'text-brand-danger'}">
                    {'+' if stats['total_pnl'] > 0 else ''}{stats['total_pnl']}%
                </span>
                <span class="text-xs px-2.5 py-1 rounded-full bg-brand-accent/50 text-gray-400 font-medium font-mono">
                    Total
                </span>
            </div>
        </div>
        <div class="bg-brand-card border border-brand-accent/50 rounded-2xl p-5 flex flex-col justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-gray-500">Avg Profit/Loss per Trade</span>
            <div class="flex items-baseline justify-between mt-4">
                <span class="text-3xl font-mono font-bold {'text-brand-success' if stats['avg_pnl'] >= 0 else 'text-brand-danger'}">
                    {'+' if stats['avg_pnl'] > 0 else ''}{stats['avg_pnl']}%
                </span>
                <span class="text-xs px-2.5 py-1 rounded-full bg-brand-accent/50 text-gray-400 font-medium font-mono">
                    Average
                </span>
            </div>
        </div>
    </div>
    """
    
    return HTMLResponse(content=oob_stats_html)
