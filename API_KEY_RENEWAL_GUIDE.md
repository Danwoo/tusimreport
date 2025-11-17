# 🔑 API 키 재발급 가이드

## 🚨 현재 상황

### Naver API
- **상태**: ❌ 비활성화/만료
- **오류**: 403 Access denied
- **조치**: 재발급 필요

### Tavily API
- **상태**: ❌ 할당량 초과
- **오류**: 432 Usage limit exceeded
- **할당량**: 무료 1,000건/월 초과
- **조치**: 업그레이드 또는 새 계정

---

## ✅ Naver API 재발급 (무료)

### 1단계: 기존 앱 확인
```
1. https://developers.naver.com/apps/#/list 접속
2. 로그인
3. "내 애플리케이션" 목록에서 현재 앱 찾기
```

### 2단계: 상태 확인
- 앱 상태가 "이용중지" 또는 "만료"인지 확인
- API 설정에서 "검색(뉴스)" API 활성화 확인

### 3단계: 새 앱 등록 (기존 앱이 안 되면)
```
1. "애플리케이션 등록" 클릭
2. 애플리케이션 이름: "tusimreport"
3. 사용 API: "검색" 선택
4. 비로그인 오픈 API: "네이버 아이디로 로그인" 선택 (필수)
5. 환경 추가: "WEB 설정" (http://localhost)
```

### 4단계: 새 키 확인
```
Client ID: (새로 생성된 ID)
Client Secret: (새로 생성된 Secret)
```

### 5단계: .env 업데이트
```bash
NAVER_CLIENT_ID=새_Client_ID
NAVER_CLIENT_SECRET=새_Client_Secret
```

**할당량**: 25,000건/일 (무료)

---

## ✅ Tavily API 업그레이드/재발급

### 옵션 A: 업그레이드 (유료)
```
1. https://tavily.com/ 접속
2. Dashboard → Billing
3. 프리미엄 플랜: $150/월 (무제한)
```

### 옵션 B: 새 계정 생성 (무료 1,000건 재획득)
```
1. 새 이메일로 https://tavily.com/ 가입
2. 새 API 키 받기
3. .env 업데이트
```

### 옵션 C: Tavily 없이 진행 (Naver만 사용)
```
- Naver만으로도 50개 뉴스 수집 가능
- 목표 100개 중 50개 달성 (50%)
```

---

## 🧪 재발급 후 테스트

### 1. .env 업데이트
```bash
nano .env

# 새 키 입력
NAVER_CLIENT_ID=새_키
NAVER_CLIENT_SECRET=새_시크릿
TAVILY_API_KEY=새_키  # (선택)
```

### 2. 테스트 실행
```bash
python3 test_p2_1_b_option_b.py
```

### 3. 예상 결과
```
✅ Naver 뉴스: 30-50개
✅ Tavily 뉴스: 40-50개 (업그레이드 시)
🔗 총 수집: 70-90개
```

---

## 📊 현재 코드 상태

**코드는 100% 정상입니다!** ✅

문제는 API 키이지 코드가 아닙니다.

증거:
- ✅ 클라이언트 초기화: 성공
- ✅ 쿼리 생성: 정상
- ✅ HTTP 요청: 정상 (API 서버까지 도달)
- ❌ API 서버 응답: 인증 실패

---

## 🚀 빠른 해결 (추천)

1. **즉시 해결**: Naver API 재발급 (5분)
   - 무료, 25,000건/일
   - 50개 뉴스 수집 가능

2. **나중에 결정**: Tavily 업그레이드
   - 필요시 프리미엄 플랜
   - 또는 Naver 50개로도 충분

---

**재발급 후 즉시 테스트하세요!**
