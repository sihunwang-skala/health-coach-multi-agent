/* Korean / English for the sign-in pages and the chat. Korean is the source text in the HTML; in English mode translateDom() swaps every known
   Korean string once at load, and dynamic text uses K(korean, english). Switching language reloads the page (one preference, shared by all pages). */
const LANG=(typeof pref==='function'&&pref('coach_lang')==='en')?'en':'ko';
const K=(ko,en)=>LANG==='en'?en:ko;
document.documentElement.lang=LANG;
const EN={
 /* sign-in */
 '로그인 · 식단·운동 코치':'Sign in · Diet & Exercise Coach','식단·운동 코치':'Diet & Exercise Coach','내 몸 상태에 맞춰 식사와 운동을 같이 살펴봐요.':'Meals and exercise, checked against your own health.',
 '로그인과 가입':'Sign in and sign up','로그인':'Sign in','가입하기':'Sign up','아이디':'Username','비밀번호':'Password','계정 만들기':'Create account','앱에서 부를 이름':'Name to show in the app',
 '예: 길동':'e.g. Alex','AI에게는 이름을 보내지 않아요.':'Your name is never sent to the AI.','영문 소문자, 숫자, 밑줄(_) 4~20자':'4–20 characters: lowercase letters, numbers, underscore (_)',
 '8자 이상, 문자와 숫자를 함께 넣어 주세요.':'At least 8 characters, with letters and numbers.','답변을 내 상황에 맞추는 데 써요. 나중에 바꿀 수 있어요.':'Used to tailor answers to you. You can change it later.',
 '나이':'Age','성별':'Sex','여성':'Female','남성':'Male','당뇨 말고 함께 있는 질환 (해당하는 것 모두)':'Other conditions besides diabetes (select all that apply)','먹거나 맞는 약':'Medicines you take or inject',
 '목록에 없는 약이 있으면 적어 주세요':'Add any medicine that is not in the list','그 밖의 약':'Other medicines','걷기와 균형':'Walking and balance','불편하지 않아요':'No difficulty',
 '균형이 불안해요':'Unsteady balance','지팡이나 보행기를 써요':'I use a cane or walker','다리 힘이 약해요':'My legs are weak','바라는 점':'Your goal','(선택)':'(optional)',
 '예: 식후 혈당 낮추기':'e.g. lower blood sugar after meals','평소 활동':'Usual activity','예: 저녁마다 공원 걷기':'e.g. walking in the park every evening','평소 식사':'Usual eating habits','예: 아침을 자주 거름':'e.g. often skip breakfast',
 '이 서비스는 의사를 대신하지 않아요.':'This service does not replace a doctor.','논문에서 찾은 일반 정보와 생활 습관 제안만 드려요. 약을 시작하거나 끊거나 바꾸는 일은 꼭 의료진과 상의해 주세요.':'It gives only general information from research papers and lifestyle suggestions. Always talk to your care team before starting, stopping or changing a medicine.',
 '응급이면 바로 119에 전화하세요.':'In an emergency, call 119 right away.','내 건강 정보를 저장하고, 이름을 뺀 건강 정보를 AI 답변에 쓰는 데 동의해요. (필수)':'I agree that my health information is stored and that my health information without my name is used for AI answers. (required)',
 '설정에서 언제든 계정과 기록을 삭제할 수 있어요.':'You can delete your account and records any time in Settings.','이전':'Back','다음':'Next','가상 사용자로 체험하기':'Try it as a demo user',
 '비밀번호 없이 바로 들어가요. 모두 가상의 인물이에요.':'No password needed. All people here are fictional.','의료진 화면으로 가기 →':'Care-team console →',"건강 정보는 이 서비스의 서버에만 저장돼요.":"Your health information is stored only on this service's server.",
 /* care-team sign-in */
 '의료진 로그인':'Care-team sign in','의료진 전용':'Care team only','의료진 콘솔 로그인':'Care-team console sign in','이용자의 건강 정보를 다루는 화면이에요. 열람 기록이 남습니다.':"This screen handles users' health information. Every access is logged.",
 '데모로 바로 보기':'View as a demo','가상 이용자의 기록만 있는 체험용 입장이에요. 열람 기록은 그대로 남아요.':'Demo access with fictional users only. Access is still logged.','데모 의료진으로 입장':'Enter as demo care team',
 '의료진 계정은 관리자가 따로 만들어 드려요. 이용자 화면은':'Care-team accounts are created separately by an administrator. User sign-in is','여기':'here','에서 로그인하세요.':'.',
 /* chat, static */
 '내 정보':'My information','메뉴 닫기':'Close menu','내 건강 요약':'My health summary','내 기록':'My records','설정':'Settings','로그아웃':'Sign out','메뉴 열기':'Open menu','코치':'Coach',
 '의료진과 이야기하기':'Talk to the care team','응급 119':'Emergency 119','대화':'Conversation','질문':'Question','식사나 운동에 대해 물어보세요':'Ask about food or exercise','보내기':'Send',
 '코치는 AI예요. 일반 건강 정보만 알려 드리고, 진단이나 처방은 하지 않아요. 약에 관한 결정은 의료진과 하세요.':'The coach is an AI. It gives general health information only, no diagnosis or prescriptions. Decisions about medicines are made with your care team.',
 '닫기':'Close','기록을 삭제할까요?':'Delete this record?','삭제하면 되돌릴 수 없어요. 확인하신 뒤에만 지워요.':'This cannot be undone. A record is deleted only after you confirm.','취소':'Cancel','삭제':'Delete',
 '글자 크기':'Text size','글자 작게':'Smaller text','가−':'A−','글자 크게':'Larger text','가＋':'A+','비밀번호 바꾸기':'Change password','현재 비밀번호':'Current password','새 비밀번호':'New password','바꾸기':'Change',
 '내 정보는 어떻게 쓰이나요?':'How is my information used?','이름은 AI에게 보내지 않아요. 나이, 질환, 약 같은 건강 정보와 질문만 답변을 만드는 데 써요. 대화는 이 서비스의 서버에 90일 동안만 보관하고, 이 기기에는 화면 파일 외에 저장하지 않아요.':'Your name is not sent to the AI. Only health information such as age, conditions and medicines, plus your question, is used to write an answer. Conversations are kept on this service\'s server for 90 days only, and nothing but the page files is stored on this device.',
 '계정 삭제':'Delete account','계정, 건강 정보, 기록, 대화 내용이 모두 지워지고 되돌릴 수 없어요.':'Your account, health information, records and conversations are all erased. This cannot be undone.','비밀번호 확인':'Confirm password',
 /* care-team console */
 '의료진 콘솔':'Care-team console','화면':'Views','개요':'Overview','알림':'Alerts','이용자':'Users','열람 기록':'Access log','← 이용자 화면':'← User screen',
 '기간':'Period','하루 메시지 수':'Messages per day','하루 메시지 수 막대 그래프':'Bar chart of messages per day','어떤 요청이 많았나':'What people asked','요청 종류별 건수 막대 그래프':'Bar chart of requests by type',
 '이용자별 메시지·알림':'Messages and alerts per user','이용자별 메시지와 알림 막대 그래프':'Bar chart of messages and alerts per user','하루 AI 비용':'AI cost per day','하루 AI 비용 선 그래프':'Line chart of AI cost per day',
 '알림 — 응급, 상담 요청, 약 변경, 다른 사람 정보 요청':'Alerts: emergencies, call requests, medicine changes, requests for another person\'s data','보기':'Show','처리 전':'Open','전체':'All',
 '이용자 (행을 누르면 자세히 봅니다)':'Users (select a row for details)','한 명 보기':'One user','위 표에서 이용자를 고르세요.':'Select a user in the table above.','의료진이 이용자 데이터를 열거나 알림을 바꾼 기록이에요.':'Records of care-team members opening user data or changing alerts.',
 /* messages from the server */
 '아이디 또는 비밀번호가 맞지 않아요.':'The username or password is incorrect.','로그인에 여러 번 실패했어요. 10분 뒤에 다시 시도해 주세요.':'Too many failed attempts. Please try again in 10 minutes.','이미 사용 중인 아이디예요.':'That username is already taken.',
 '비밀번호는 8자 이상이어야 해요.':'The password must be at least 8 characters.','비밀번호에 문자와 숫자를 함께 넣어 주세요.':'Please use both letters and numbers in the password.','개인정보와 건강정보 이용에 동의해 주세요.':'Please agree to the use of your personal and health information.',
 '성별을 선택해 주세요.':'Please select your sex.','로그인이 필요해요.':'Please sign in.','의료진 로그인이 필요해요.':'Care-team sign-in is required.','허용되지 않은 요청이에요.':'This request is not allowed.','현재 비밀번호가 맞지 않아요.':'The current password is incorrect.',
 '비밀번호가 맞지 않아요.':'The password is incorrect.','입력한 내용을 다시 확인해 주세요.':'Please check what you entered.','문제가 생겼어요. 잠시 뒤에 다시 해 주세요.':'Something went wrong. Please try again in a moment.',
 '아이디는 영문 소문자, 숫자, 밑줄(_) 4~20자예요.':'The username must be 4–20 characters: lowercase letters, numbers, underscore (_).'
};
const tr=s=>(LANG==='en'&&Object.prototype.hasOwnProperty.call(EN,s))?EN[s]:s;
function translateDom(){
 if(LANG!=='en')return;
 const w=document.createTreeWalker(document.documentElement,NodeFilter.SHOW_TEXT,{acceptNode:n=>/^(SCRIPT|STYLE)$/.test(n.parentElement.tagName)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
 const nodes=[];while(w.nextNode())nodes.push(w.currentNode);
 nodes.forEach(n=>{const t=n.nodeValue.trim();if(t&&Object.prototype.hasOwnProperty.call(EN,t))n.nodeValue=n.nodeValue.replace(t,EN[t])});
 document.querySelectorAll('[placeholder],[aria-label],[title]').forEach(e=>['placeholder','aria-label','title'].forEach(a=>{const v=e.getAttribute(a);if(v&&Object.prototype.hasOwnProperty.call(EN,v))e.setAttribute(a,EN[v])}));
}
function mountLang(el){
 if(!el)return;
 el.innerHTML='<button type="button" data-l="ko" aria-pressed="'+(LANG==='ko')+'">한국어</button><button type="button" data-l="en" aria-pressed="'+(LANG==='en')+'">EN</button>';
 el.setAttribute('aria-label',K('언어','Language'));
 el.onclick=e=>{const b=e.target.closest('button');if(!b||b.dataset.l===LANG)return;setPref('coach_lang',b.dataset.l);location.reload()};
}
