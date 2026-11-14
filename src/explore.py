"""Read-only M4 exploration. Standard-library SVG plots keep offline builds portable.

Source text parsing and correction belong in clean.py; this module only queries
the cleaned layer, chooses explicit analysis cohorts and computes summaries.
"""
from collections import Counter, defaultdict
import hashlib
from html import escape
import json
import math
from pathlib import Path
import random
import statistics as st
import textwrap

from db import ROOT, DEFAULT_DB, connect

# Source fields pivoted by sql/queries/m4_cohort.sql; each must be unique per model.
ANALYTICAL_FIELDS = ['price', 'os', 'year', 'internalmemory', 'displaysize']

COLORS = {'Samsung': '#2463a5', 'Xiaomi': '#cf661c', 'Huawei': '#248878',
          'Sony': '#9654a1', 'All': '#35485e'}


def quantile(values, p):
    """Linear-interpolated percentile (same rule as numpy's default); None if empty."""
    a = sorted(values)
    if not a:
        return None
    pos = (len(a)-1)*p
    lo = int(pos)
    return a[lo] + (a[min(lo+1, len(a)-1)]-a[lo])*(pos-lo)


def summary(values):
    """n, mean, median, p95, min and max of one group; statistics are None when n=0."""
    a = list(values)
    return dict(n=len(a), mean=st.mean(a) if a else None,
                median=st.median(a) if a else None, p95=quantile(a, .95),
                min=min(a) if a else None, max=max(a) if a else None)


def pearson(x, y):
    """Pearson correlation; None for fewer than three pairs or a constant variable."""
    if len(x) < 3:
        return None
    mx, my = st.mean(x), st.mean(y)
    xx, yy = sum((v-mx)**2 for v in x), sum((v-my)**2 for v in y)
    return sum((a-mx)*(b-my) for a, b in zip(x, y))/math.sqrt(xx*yy) if xx*yy else None


def ranks(values):
    """1-based ranks with ties given their average rank, as Spearman requires."""
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0]*len(values)
    i = 0
    while i < len(order):
        j = i+1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        for index in order[i:j]:
            result[index] = (i+j-1)/2+1
        i = j
    return result


def correlation(rows):
    """Pearson and Spearman of RAM against price on identical complete pairs."""
    x, y = [r['ram'] for r in rows], [r['price'] for r in rows]
    return dict(n=len(rows), pearson=pearson(x, y), spearman=pearson(ranks(x), ranks(y)))


def display_split(joint, threshold):
    """RAM-price correlations on phone-sized and large screens (>= threshold inches).

    Display size is a measured attribute, not a device class: the large-screen
    group can hold tablets and foldable phones alike, so it is reported as
    measured and never relabelled here. Pairs without a display size are counted
    and left out of both groups.
    """
    measured = [r for r in joint if r['display_in'] is not None]
    small = [r for r in measured if r['display_in'] < threshold]
    large = [r for r in measured if r['display_in'] >= threshold]
    return dict(threshold_in=threshold, display_missing=len(joint)-len(measured),
                phone_sized=correlation(small), large_screen=correlation(large),
                large_screen_by_brand=dict(sorted(Counter(r['brand'] for r in large).items())))


def ram_levels(joint, params):
    """Price median and quartiles at each recorded RAM level, all pairs and phone-sized screens.

    RAM is recorded at discrete levels, so per-level medians are the binned
    view of the scatter. A level needs min_joint pairs to be plotted; thinner
    levels stay in the table with eligible=False.
    """
    def stats(prices, prefix):
        return {prefix+'n': len(prices), prefix+'median': st.median(prices) if prices else None,
                prefix+'q1': quantile(prices, .25), prefix+'q3': quantile(prices, .75),
                prefix+'eligible': len(prices) >= params['min_joint']}
    result = []
    for (ram,), group in sorted(grouped(joint, ('ram',)).items()):
        phone = [r['price'] for r in group
                 if r['display_in'] is not None and r['display_in'] < params['large_display_in']]
        result.append(dict(ram=ram, **stats([r['price'] for r in group], ''), **stats(phone, 'phone_')))
    return result


def read_cohort(con, params, flags=None):
    """One row per selected catalog model; flags override the primary numeric filter."""
    bindings = dict(currency=params['currency'], os=params['os'],
                    start=params['start_year'], end=params['end_year'],
                    brands=json.dumps(params['brands']),
                    flags=json.dumps(flags if flags is not None else params['flags']))
    return [dict(r) for r in con.execute((ROOT/'sql/queries/m4_cohort.sql').read_text(), bindings)]


def raw_summary(con, params):
    """Naive M2 baseline: mean of the raw `About … EUR` cast per brand, no flags."""
    return [dict(r) for r in con.execute((ROOT/'sql/queries/m4_raw.sql').read_text(),
        dict(start=params['start_year'], end=params['end_year'],
             brands=json.dumps(params['brands']), price_pattern='About % EUR', os_pattern='Android%'))]


def grouped(rows, keys):
    """Group row dicts by a tuple of key columns."""
    result = defaultdict(list)
    for row in rows:
        result[tuple(row[k] for k in keys)].append(row)
    return result


def coverage(rows, params, keys=('brand', 'year')):
    """Price coverage and summaries per group, with the coverage rule as `eligible`.

    The denominator is every catalog model in the group, priced or not.
    """
    result = []
    for key, group in sorted(grouped(rows, keys).items()):
        priced = [r for r in group if r['price'] is not None]
        joint = [r for r in priced if r['ram'] is not None]
        rec = dict(zip(keys, key))
        rec.update(catalog_n=len(group), price_n=len(priced), joint_n=len(joint),
                   price_coverage=len(priced)/len(group), ram_price_coverage=len(joint)/len(group),
                   **{k:v for k,v in summary(r['price'] for r in priced).items() if k!='n'})
        rec['eligible'] = (len(group) >= params['min_models'] and
                           len(priced) >= params['min_prices'] and
                           len(priced)/len(group) >= params['min_coverage'])
        result.append(rec)
    return result


def paired_bootstrap(differences, params, block_length):
    """Circular paired moving-block bootstrap of chronological year contrasts.

    Resampling a common year contrast keeps both brands together. Blocks retain
    short-range temporal dependence; this is exploratory with few cohort years.
    """
    rng = random.Random(params['seed'])
    n = len(differences)
    if n < 3:
        raise ValueError('Fewer than three common eligible years: no interval supported')
    draws = []
    for _ in range(params['bootstrap_reps']):
        sample = []
        while len(sample) < n:
            start = rng.randrange(n)
            sample.extend(differences[(start+j) % n] for j in range(block_length))
        draws.append(st.mean(sample[:n]))
    return [quantile(draws, .025), quantile(draws, .975)]


class SVG:
    """Small vector plotting backend: shared scales, zero-based bars, captions."""
    def __init__(self, title, subtitle, caption, width=1200, height=780):
        self.w, self.h = width, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
                      '<rect width="100%" height="100%" fill="#f8fafc"/>',
                      '<style>text{font-family:Arial,sans-serif;fill:#24364b} .grid{stroke:#dde5ed;stroke-width:1}</style>',
                      '<title>'+escape(title)+'</title>']
        self.text(35, 38, title, 23, weight='bold')
        self.text(35, 66, subtitle, 14)
        caption_lines=[part for line in caption for part in textwrap.wrap(line,width=175)]
        for i, line in enumerate(caption_lines):
            self.text(35, height-22-19*(len(caption_lines)-1)+19*i, line, 12)

    def text(self, x, y, text, size=12, anchor='start', weight='normal', fill=None):
        extra = '' if fill is None else f' style="fill:{fill}"'
        self.parts.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}"{extra}>{escape(str(text))}</text>')

    def line(self, x1, y1, x2, y2, color='#ccd7e2', width=1, dash=False):
        d = ' stroke-dasharray="5 4"' if dash else ''
        self.parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="{width}"{d}/>')

    def rect(self, x, y, w, h, color, opacity=1):
        self.parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(0,w):.2f}" height="{max(0,h):.2f}" fill="{color}" opacity="{opacity}"/>')

    def circle(self, x, y, r, color, opacity=.45):
        self.parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{color}" opacity="{opacity}"/>')

    def path(self, points, color, width=2):
        if len(points) < 2:
            return
        d = 'M '+' L '.join(f'{x:.2f},{y:.2f}' for x,y in points)
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"/>')

    def axes(self, x, y, w, h, xmax, ymax, xlabel, ylabel, title='', xmin=0, ymin=0, xticks=None):
        def xy(a,b):
            return x+(a-xmin)/(xmax-xmin)*w, y+h-(b-ymin)/(ymax-ymin)*h
        self.text(x, y-15, title, 14, weight='bold')
        for i in range(5):
            b = ymin+(ymax-ymin)*i/4
            _, py = xy(xmin,b)
            self.line(x,py,x+w,py)
            self.text(x-9,py+4,f'{b:,.2g}' if ymax <= 2 else f'{b:,.0f}',11,'end')
        ticks = xticks if xticks is not None else [xmin+(xmax-xmin)*i/4 for i in range(5)]
        for a in ticks:
            px, _ = xy(a,ymin)
            tick=f'{a:.0f}' if 'Announcement' in xlabel else f'{a:,.0f}'
            self.text(px,y+h+20,tick,11,'middle')
        self.line(x,y+h,x+w,y+h,'#8292a5')
        self.text(x+w/2,y+h+43,xlabel,12,'middle')
        self.text(x,y-34,ylabel,11)
        return xy

    def save(self, path):
        path.write_text('\n'.join(self.parts+['</svg>'])+'\n',encoding='utf-8')


def captions(params, n, extra=''):
    """Two caption lines stating n, cohort, currency and the flag filter."""
    return [f'n={n:,} current catalog IDs; Android; {params["start_year"]}-{params["end_year"]} announcement cohorts; {params["currency"]}. '+extra,
            'Numeric flags: '+', '.join(params['flags'])+'. OS: mapped; year: ok. Catalog amounts, not verified launch MSRP.']


def plot_shape(rows, params, directory):
    priced = [r for r in rows if r['price'] is not None]
    panels = [('All', priced)]+[(b,[r for r in priced if r['brand']==b]) for b in params['brands']]
    xmax = (math.floor(max(r['price'] for r in priced)/params['bin_width'])+1)*params['bin_width']
    all_counts = [Counter(int(r['price']//params['bin_width']) for r in group) for _,group in panels]
    ymax = max(max(c.values(),default=0) for c in all_counts)*1.12
    s = SVG('Catalog prices have a long upper tail', 'Question: what does a typical catalog amount hide? Shared axes across all five panels.',captions(params,len(priced),'Bin width: EUR '+str(params['bin_width'])+'.'),height=900)
    e = SVG('The ECDF exposes differences beyond the median','Question: what share of each group is at or below each EUR price?',captions(params,len(priced),'Dashed line: cumulative share 0.5.'),height=900)
    for index,(brand,group) in enumerate(panels):
        x,y=75+(index%3)*395,145+(index//3)*340
        xy=s.axes(x,y,300,225,xmax,ymax,'Catalog price (EUR)','Catalog models (count)',f'{brand} (n={len(group)})')
        for bin_index,count in all_counts[index].items():
            px,py=xy(bin_index*params['bin_width'],count)
            end,base=xy((bin_index+1)*params['bin_width'],0)
            s.rect(px,py,end-px-1,base-py,COLORS[brand])
        ex=e.axes(x,y,300,225,xmax,1,'Catalog price (EUR)','Cumulative share',f'{brand} (n={len(group)})')
        points=[ex(0,0)]
        for i,v in enumerate(sorted(r['price'] for r in group)):
            points.extend([ex(v,i/len(group)),ex(v,(i+1)/len(group))])
        e.path(points,COLORS[brand]);e.line(*ex(0,.5),*ex(xmax,.5),'#8292a5',1,True)
    s.save(directory/'01_price_histogram.svg');e.save(directory/'02_price_ecdf.svg')


def plot_coverage(annual, rows, params, directory):
    s=SVG('Recent catalog cohorts lose usable EUR price coverage', 'Question: which brand-years support a price comparison? Cells show usable / catalog models.',captions(params,len(rows),'Grey = no catalog models; * = passes coverage rule.'),height=680)
    years=list(range(params['start_year'],params['end_year']+1))
    for j,year in enumerate(years):
        s.text(160+j*63+29,130,str(year),12,'middle')
    lookup={(r['brand'],r['year']):r for r in annual}
    for i,brand in enumerate(params['brands']):
        y=152+i*92;s.text(40,y+42,brand,15,weight='bold')
        for j,year in enumerate(years):
            r=lookup.get((brand,year));x=160+j*63
            share=r['price_coverage'] if r else 0
            color=f'rgb({int(235-165*share)},{int(242-105*share)},{int(249-65*share)})' if r else '#e5e7eb'
            s.rect(x,y,58,72,color)
            label=f'{r["price_n"]}/{r["catalog_n"]}' if r else '0/0'
            s.text(x+29,y+30,label,11,'middle',fill='#ffffff' if share>.7 else '#24364b')
            s.text(x+29,y+53,('* ' if r and r['eligible'] else '')+(f'{share:.0%}' if r else 'NA'),11,'middle',fill='#ffffff' if share>.7 else '#24364b')
    s.text(160,565,f'Rule: catalog n >= {params["min_models"]}; usable prices >= {params["min_prices"]}; usable EUR / catalog >= {params["min_coverage"]:.0%}.',14)
    s.text(160,590,'Announcement year (calendar cohort; no timestamp/timezone conversion)',12)
    s.save(directory/'03_coverage.svg')


def plot_time(annual, rows, params, directory):
    s=SVG('Year and five-year summaries answer different cohort questions','Question: does the typical EUR catalog amount change across device generations?',captions(params,sum(r['price'] is not None for r in rows),'Only groups passing coverage rule are plotted; lines break at failed/missing years.'),height=740)
    period_rows=[dict(r,period=(r['year']//5)*5) for r in rows]
    periods=coverage(period_rows,params,('brand','period'))
    ymax=math.ceil(max(r['median'] for r in annual if r['eligible'])/100)*100
    for panel,(data,key,xmin,xmax,ticks) in enumerate([(annual,'year',2010,2025,[2010,2015,2020,2025]),(periods,'period',2010,2025,[2010,2015,2020,2025])]):
        xy=s.axes(85+panel*580,155,475,395,xmax,ymax,'Announcement '+('year' if key=='year' else 'five-year bin start'),'Median catalog price (EUR)', 'Annual cohorts' if key=='year' else 'Five-year cohorts',xmin=xmin,xticks=ticks)
        for brand in params['brands']:
            previous=None
            for r in [v for v in data if v['brand']==brand]:
                if not r['eligible']:
                    previous=None;continue
                point=xy(r[key],r['median'])
                if previous and r[key]-previous[0] == (1 if key=='year' else 5):
                    s.line(*previous[1],*point,COLORS[brand],2)
                s.circle(*point,4,COLORS[brand],1);previous=(r[key],point)
    for i,b in enumerate(params['brands']):
        s.text(85+i*270,615,b,14,weight='bold',fill=COLORS[b])
    s.save(directory/'04_announcement_cohorts.svg')
    return periods


def plot_relationship(rows, params, directory):
    joint=[r for r in rows if r['price'] is not None and r['ram'] is not None]
    xmax=math.ceil(max(r['ram'] for r in joint)/2)*2
    ymax=math.ceil(max(r['price'] for r in joint)/200)*200
    s=SVG('RAM and price move together in a selected subset','Question: is the RAM-price relationship consistent within each brand?',captions(params,len(joint),'Only explicit single storage/RAM pairs; shared axes; no jitter or fitted model.'),height=920)
    for i,b in enumerate(params['brands']):
        group=[r for r in joint if r['brand']==b]
        xy=s.axes(85+(i%2)*585,150+(i//2)*340,475,225,xmax,ymax,'RAM (SI GB)','Catalog price (EUR)',f'{b}: n={len(group)}')
        for r in group:
            s.circle(*xy(r['ram'],r['price']),3,COLORS[b])
    s.save(directory/'05_ram_price.svg')


def ram_label(ram):
    """Short RAM tick label: 0.512, 1, 1.5, 12."""
    return f'{ram:g}'


def plot_ram_levels(levels, joint, params, directory):
    """Binned medians: price median and IQR per RAM level on a log2 RAM axis."""
    shown = [r for r in levels if r['eligible']]
    thin = [r for r in levels if not r['eligible']]
    overall = st.median(r['price'] for r in joint)
    small = f'display < {params["large_display_in"]:g} in'
    # The title states the finding only when the data still support it.
    middle = [r['median'] for r in shown if 1 <= r['ram'] <= 4]
    upper = [r['median'] for r in shown if r['ram'] > 4]
    if middle and upper and min(upper) > max(middle):
        title = f'Median price stays at EUR {min(middle):,.0f}-{max(middle):,.0f} from 1 to 4 GB RAM and is higher only above 4 GB'
    else:
        title = 'Median catalog price by RAM level'
    s = SVG(title, 'Question: does the typical price rise with every RAM step, or only at the ends? Dot = median; bar = interquartile range.',
            captions(params, len(joint), f'Only explicit single storage/RAM pairs. A level needs n >= {params["min_joint"]} pairs; '
                     f'{len(thin)} thinner levels ({sum(r["n"] for r in thin)} pairs) are not drawn. Dashed line: median of all pairs.'),
            height=760)
    xs = [math.log2(r['ram']) for r in shown]
    xmin, xmax = min(xs)-.5, max(xs)+.5
    ymax = math.ceil(max([r['q3'] for r in shown]+[r['phone_q3'] for r in shown if r['phone_eligible']])/400)*400
    x0, y0, w, h = 95, 150, 1000, 390
    xy = s.axes(x0, y0, w, h, xmax, ymax, '', 'Catalog price (EUR)', xmin=xmin, xticks=[])
    s.line(*xy(xmin, overall), *xy(xmax, overall), '#8292a5', 1, True)
    s.text(x0+w-4, xy(xmin, overall)[1]-6, f'all-pairs median EUR {overall:,.0f}', 11, 'end')
    series = [('', COLORS['All'], 'All pairs', -.07), ('phone_', '#b42318', 'Pairs with '+small, .07)]
    for prefix, color, _, offset in series:
        for r in shown:
            if not r[prefix+'eligible']:
                continue
            x = math.log2(r['ram'])+offset
            s.line(*xy(x, r[prefix+'q1']), *xy(x, r[prefix+'q3']), color, 3)
            s.circle(*xy(x, r[prefix+'median']), 5, color, 1)
    s.text(x0-9, y0+h+20, 'RAM', 11, 'end')
    s.text(x0-9, y0+h+38, 'n all', 11, 'end', fill=COLORS['All'])
    s.text(x0-9, y0+h+56, 'n <'+f'{params["large_display_in"]:g} in', 11, 'end', fill='#b42318')
    for r in shown:
        px, _ = xy(math.log2(r['ram']), 0)
        s.text(px, y0+h+20, ram_label(r['ram']), 11, 'middle')
        s.text(px, y0+h+38, r['n'], 11, 'middle', fill=COLORS['All'])
        s.text(px, y0+h+56, r['phone_n'] if r['phone_eligible'] else f'{r["phone_n"]} (thin)', 11, 'middle', fill='#b42318')
    s.text(x0+w/2, y0+h+80, 'RAM level (SI GB, log2 spacing; each level is one recorded value)', 12, 'middle')
    for i, (_, color, label, _) in enumerate(series):
        s.circle(x0+620+i*190, 112, 5, color, 1)
        s.text(x0+632+i*190, 116, label, 12, fill=color)
    s.save(directory/'07_ram_binned_medians.svg')


def comparison(annual, rows, params, directory):
    a,b=params['comparison']
    lookup={(r['brand'],r['year']):r for r in annual}
    paired=[]
    for year in range(params['comparison_start'],params['end_year']+1):
        left,right=lookup.get((a,year)),lookup.get((b,year))
        if left and right and left['eligible'] and right['eligible']:
            paired.append(dict(year=year,difference=left['median']-right['median'],a_n=left['price_n'],b_n=right['price_n'],a_median=left['median'],b_median=right['median']))
    years=[r['year'] for r in paired]
    if years != list(range(min(years),max(years)+1)):
        raise ValueError('Block bootstrap requires contiguous common eligible years')
    diffs=[r['difference'] for r in paired]
    ci=paired_bootstrap(diffs,params,params['block_length'])
    iid_ci=paired_bootstrap(diffs,params,1)
    pooled={brand:summary(r['price'] for r in rows if r['brand']==brand and r['price'] is not None) for brand in [a,b]}
    common={brand:summary(r['price'] for r in rows if r['brand']==brand and r['year'] in years and r['price'] is not None) for brand in [a,b]}
    point=st.mean(diffs)
    result=dict(a=a,b=b,years=years,paired=paired,estimate=point,ci95=ci,iid_year_ci95=iid_ci,
                pooled=pooled,common_years=common,pooled_median_difference=pooled[a]['median']-pooled[b]['median'],
                common_pooled_median_difference=common[a]['median']-common[b]['median'])
    low=min(0,min(diffs),ci[0])-40;high=max(0,max(diffs),ci[1])+40
    s=SVG(f'{a} minus {b}: equal-year median contrast {point:+.0f} EUR', 'Question: how does the comparison change after giving common cohort years equal weight?',captions(params,sum(r['a_n']+r['b_n'] for r in paired),f'{len(years)} paired years; 95% interval; {params["block_length"]}-year circular blocks.'),height=740)
    xy=s.axes(95,160,670,380,max(years)+1,high,'Announcement year','Median difference (EUR)',f'{a} - {b}; zero = no difference',xmin=min(years)-1,ymin=low,xticks=years)
    s.line(*xy(min(years)-1,0),*xy(max(years)+1,0),'#8292a5',1,True)
    for r in paired:
        px,py=xy(r['year'],r['difference']);_,base=xy(r['year'],0)
        s.rect(px-18,min(py,base),36,abs(py-base),'#2463a5')
        s.text(px,py-10,f'{r["difference"]:+.0f}',12,'middle')
    ex=s.axes(900,160,200,380,1,high,'Equal-year estimate','EUR difference','Paired block bootstrap',ymin=low,xticks=[])
    s.line(*ex(0,0),*ex(1,0),'#8292a5',1,True)
    s.line(*ex(.5,ci[0]),*ex(.5,ci[1]),'#cf661c',4);s.circle(*ex(.5,point),7,'#cf661c',1)
    for v in ci:
        s.line(*ex(.4,v),*ex(.6,v),'#cf661c',2)
    s.text(95,615,f'95% interval: [{ci[0]:+.1f}, {ci[1]:+.1f}] EUR; {params["bootstrap_reps"]:,} replicates, seed {params["seed"]}.',14)
    s.save(directory/'06_brand_comparison.svg')
    return result


def analyze(con, params, output):
    """Run every M4 query, write the seven figures and return the aggregate results."""
    rows=read_cohort(con,params)
    strict=read_cohort(con,params,params['strict_flags'])
    annual=coverage(rows,params)
    groups=coverage(rows,params,('brand',))
    figures=output/'figures';figures.mkdir(parents=True,exist_ok=True)
    # Plot each relationship before calculating its coefficients.
    plot_shape(rows,params,figures);plot_coverage(annual,rows,params,figures)
    periods=plot_time(annual,rows,params,figures)
    plot_relationship(rows,params,figures)
    joint=[r for r in rows if r['price'] is not None and r['ram'] is not None]
    levels=ram_levels(joint,params)
    plot_ram_levels(levels,joint,params,figures)
    xcut=quantile([r['ram'] for r in joint],.99);ycut=quantile([r['price'] for r in joint],.99)
    trimmed=[r for r in joint if r['ram']<=xcut and r['price']<=ycut]
    by_brand={b:correlation([r for r in joint if r['brand']==b]) for b in params['brands']}
    within=[]
    for key,group in sorted(grouped(joint,('brand','year')).items()):
        if len(group)>=params['min_joint']:
            within.append(dict(brand=key[0],year=key[1],**correlation(group)))
    # Demean within brand x year to remove common group-level patterns.
    # Use groups with >= min_joint for this sensitivity; report the retained n.
    residuals=[]
    for _,group in grouped(joint,('brand','year')).items():
        if len(group)>=params['min_joint']:
            mx,my=st.mean(r['ram'] for r in group),st.mean(r['price'] for r in group)
            residuals.extend(dict(ram=r['ram']-mx,price=r['price']-my) for r in group)
    counts=Counter(r['brand'] for r in joint)
    influence={b:correlation([r for r in joint if r['brand']!=b]) for b in params['brands']}
    # Device-type check: does a screen-size group carry the pooled association?
    screens=display_split(joint,params['large_display_in'])
    large_pairs=sorted((dict(name=r['name'],brand=r['brand'],year=r['year'],display_in=r['display_in'],
                             ram=r['ram'],price=r['price']) for r in joint
                        if r['display_in'] is not None and r['display_in']>=params['large_display_in']),
                       key=lambda r:(-r['price'],r['name']))
    bins=[]
    priced=[r['price'] for r in rows if r['price'] is not None]
    for width in params['bin_trials']:
        hist=Counter(int(v//width) for v in priced)
        bins.append(dict(width=width,nonempty_bins=len(hist),peak_bin_n=max(hist.values()),upper=max(priced),n=len(priced)))
    duplicates=list(con.execute((ROOT/'sql/queries/m4_audit_duplicates.sql').read_text(),
        dict(fields=json.dumps(ANALYTICAL_FIELDS))))
    if duplicates:
        raise ValueError('Repeated analytical fields need a cleaning decision before pivoting')
    if con.execute('SELECT COUNT(*) FROM phone_identity_map').fetchone()[0]:
        raise ValueError('New identity decisions require a reviewed canonical observation rule')
    contrast=comparison(annual,rows,params,figures)
    allpairs=[]
    for i,a in enumerate(params['brands']):
        for b in params['brands'][i+1:]:
            left=next(r for r in groups if r['brand']==a);right=next(r for r in groups if r['brand']==b)
            allpairs.append(dict(a=a,b=b,pooled_median_difference=left['median']-right['median'],a_n=left['price_n'],b_n=right['price_n']))
    raw=raw_summary(con,params)
    strict_groups=coverage(strict,params,('brand',))
    no_rule=[dict(r,eligible=True) for r in annual]
    # Sensitivity preserves the year-median estimand while dropping the rule.
    a,b=params['comparison'];unfiltered=[]
    for year in range(params['comparison_start'],params['end_year']+1):
        pair=[next((r for r in no_rule if r['brand']==brand and r['year']==year),None) for brand in [a,b]]
        if all(r and r['price_n'] for r in pair):
            unfiltered.append(dict(year=year,difference=pair[0]['median']-pair[1]['median'],a_n=pair[0]['price_n'],b_n=pair[1]['price_n']))
    return dict(params=params,catalog_n=con.execute('SELECT COUNT(*) FROM phone').fetchone()[0],
                cohort_n=len(rows),raw=raw,groups=groups,strict_groups=strict_groups,
                annual=annual,periods=periods,bins=bins,relationship=correlation(joint),
                trimmed=correlation(trimmed),trim_removed=len(joint)-len(trimmed),
                trim_thresholds=dict(ram_gb=xcut,price_eur=ycut),by_brand=by_brand,
                within_brand_year=within,group_demeaned=correlation(residuals),
                leave_one_brand_out=influence,display_split=screens,large_screen_pairs=large_pairs,
                ram_levels=levels,
                comparison=contrast,all_pairs=allpairs,
                without_coverage_rule=dict(estimate=st.mean(r['difference'] for r in unfiltered),paired=unfiltered),
                retrieval_range=list(con.execute('SELECT MIN(retrieved_at),MAX(retrieved_at) FROM phone').fetchone()),
                cohort_year_range=[min(r['year'] for r in rows),max(r['year'] for r in rows)],
                eligible_annual_groups=sum(r['eligible'] for r in annual),total_annual_groups=len(annual),
                overall=summary(priced),joint_counts=dict(counts),
                audit=dict(duplicate_analytical_fields=0,identity_mappings=0))


def markdown_table(rows, columns):
    """Render row dicts as a Markdown table; floats get three decimals."""
    def fmt(v):
        if v is None:return 'NA'
        if isinstance(v,bool):return 'yes' if v else 'no'
        if isinstance(v,float):return f'{v:,.3f}'
        return str(v)
    return '\n'.join(['| '+' | '.join(columns)+' |','|'+'|'.join('---' for _ in columns)+'|']+['| '+' | '.join(fmt(r.get(k)) for k in columns)+' |' for r in rows])


def print_table(rows, columns):
    print(markdown_table(rows,columns))


def database_hash(path):
    """SHA-256 of the database file, compared before and after the notebook runs."""
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()
