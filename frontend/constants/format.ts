/** '6:12' + 'PM' (디자인의 시각 표기) */
export function clock(iso: string | Date): { hm: string; ap: string } {
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  const h = d.getHours();
  return { hm: `${h % 12 || 12}:${String(d.getMinutes()).padStart(2, '0')}`, ap: h < 12 ? 'AM' : 'PM' };
}

export function clockText(iso: string | Date): string {
  const c = clock(iso);
  return `${c.hm} ${c.ap}`;
}

/** '오늘 6:30 PM' / '내일 9:00 AM' / '10월 8일 6:30 PM' */
export function dayClock(d: Date): string {
  const today = new Date();
  const diff = Math.round(
    (new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() -
      new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()) /
      86400000,
  );
  const day = diff === 0 ? '오늘' : diff === 1 ? '내일' : `${d.getMonth() + 1}월 ${d.getDate()}일`;
  return `${day} ${clockText(d)}`;
}

export function monthDay(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

export const won = (n: number) => n.toLocaleString('ko-KR');

/** 'PARKING_11' → '11번 구역', 'CHARGER_01' → '1번' */
export function zoneLabel(id: string | null | undefined): string | null {
  const m = id?.match(/PARKING_(\d+)/);
  return m ? `${Number(m[1])}번 구역` : null;
}

export function chargerNo(id: string | null | undefined): string | null {
  const m = id?.match(/(\d+)$/);
  return m ? `충전기 ${Number(m[1])}번` : null;
}

/** '10월 3일 (금)' */
export function dayWithWeek(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  return `${d.getMonth() + 1}월 ${d.getDate()}일 (${'일월화수목금토'[d.getDay()]})`;
}

/** 충전 시간(분). 아직 끝나지 않았으면 null */
export function minutesBetween(a: string, b: string | null): number | null {
  return b ? Math.max(0, Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000)) : null;
}
