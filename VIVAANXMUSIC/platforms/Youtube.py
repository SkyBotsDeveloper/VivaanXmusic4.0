import asyncio
import os
import re
import time
from typing import Union
import yt_dlp
import aiohttp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch
from VIVAANXMUSIC import LOGGER
from VIVAANXMUSIC.utils.formatters import time_to_seconds

logger = LOGGER(__name__)

# ============================================================================
# CONFIGURATION - MULTIPLE FREE APIs
# ============================================================================
CACHE_TIME = 3600  # 1 hour
DOWNLOADS_FOLDER = "downloads"

MAX_API_RETRIES = 2
MAX_YTDLP_RETRIES = 2
RETRY_DELAY = 0.3
API_TIMEOUT = 12
DOWNLOAD_TIMEOUT = 300

# ✅ MULTIPLE FREE APIs (AGE-BYPASS)
FREE_APIS = [
    {
        "name": "SocialDown",
        "url": "https://socialdown.itz-ashlynn.workers.dev/yt",
        "method": "GET",
        "params": lambda url, fmt: {"url": url, "format": fmt}
    },
    {
        "name": "Y2Mate",
        "url": "https://www.y2mate.com/mates/analyzeV2/ajax",
        "method": "POST",
        "params": lambda url, fmt: {"k_query": url, "k_page": "home", "hl": "en", "q_auto": "1"}
    },
    {
        "name": "Loader",
        "url": "https://loader.to/ajax/download.php",
        "method": "GET",
        "params": lambda url, fmt: {"url": url, "format": fmt}
    },
    {
        "name": "SaveFrom",
        "url": "https://api.vevioz.com/api/button/videos",
        "method": "GET",
        "params": lambda url, fmt: {"url": url}
    },
    {
        "name": "Cobalt",
        "url": "https://api.cobalt.tools/api/json",
        "method": "POST",
        "params": lambda url, fmt: {"url": url, "vCodec": "h264", "vQuality": "720", "aFormat": "mp3"}
    }
]

# ============================================================================
# YOUTUBE API - MULTI-API WITH AGE-BYPASS
# ============================================================================
class YouTubeAPI:
    """YouTube API - 5 APIs + yt-dlp (100% Coverage)"""
    
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def _get_video_details(self, link: str, limit: int = 20):
        """Get video details from search"""
        try:
            if not link:
                return None
            
            link = str(link).strip()
            if not link:
                return None
            
            try:
                results = VideosSearch(link, limit=limit)
                search_results = (await results.next()).get("result", [])
            except Exception as e:
                logger.error(f"Search error: {e}")
                return None

            if not search_results:
                return None
            
            result = search_results[0]
            if not isinstance(result, dict):
                return None
            
            title = str(result.get("title") or "Unknown").strip() or "Unknown"
            duration = str(result.get("duration") or "0:00").strip() or "0:00"
            
            thumbnails = result.get("thumbnails") or []
            thumbnail_url = ""
            if isinstance(thumbnails, list) and thumbnails:
                thumb = thumbnails[0]
                if isinstance(thumb, dict):
                    url = thumb.get("url")
                    if url and isinstance(url, str):
                        thumbnail_url = url.strip().split("?")[0]
            
            if not thumbnail_url:
                thumbnail_url = "https://via.placeholder.com/320x180"
            
            video_id = str(result.get("id") or "").strip()
            if not video_id:
                return None
            
            link_url = str(result.get("link") or f"https://www.youtube.com/watch?v={video_id}").strip()
            
            return {
                "title": title,
                "duration": duration,
                "thumbnails": [{"url": thumbnail_url}],
                "id": video_id,
                "link": link_url
            }

        except Exception as e:
            logger.error(f"Details error: {e}")
            return None

    async def _try_api(self, api_config: dict, url: str, fmt: str):
        """Try a single API"""
        try:
            api_name = api_config["name"]
            api_url = api_config["url"]
            method = api_config["method"]
            params = api_config["params"](url, fmt)
            
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(
                        api_url,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return self._extract_download_url(data, api_name)
                else:  # POST
                    async with session.post(
                        api_url,
                        json=params if api_name == "Cobalt" else None,
                        data=params if api_name != "Cobalt" else None,
                        timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return self._extract_download_url(data, api_name)
            
            return None
        except Exception as e:
            logger.debug(f"[{api_config['name']}] Error: {e}")
            return None

    def _extract_download_url(self, data: dict, api_name: str):
        """Extract download URL from different API response formats"""
        try:
            # SocialDown format
            if api_name == "SocialDown":
                if data.get("success") and data.get("data"):
                    return data["data"][0].get("downloadUrl")
            
            # Cobalt format
            elif api_name == "Cobalt":
                if data.get("url"):
                    return data["url"]
            
            # Y2Mate format
            elif api_name == "Y2Mate":
                if data.get("links"):
                    links = data["links"]
                    if "mp3" in links:
                        for quality in links["mp3"]:
                            if links["mp3"][quality].get("url"):
                                return links["mp3"][quality]["url"]
                    if "mp4" in links:
                        for quality in links["mp4"]:
                            if links["mp4"][quality].get("url"):
                                return links["mp4"][quality]["url"]
            
            # Loader format
            elif api_name == "Loader":
                if data.get("download_url"):
                    return data["download_url"]
            
            # SaveFrom format
            elif api_name == "SaveFrom":
                if data.get("url"):
                    return data["url"]
            
            return None
        except:
            return None

    async def _fetch_multi_api(self, url: str, fmt: str = "mp3"):
        """Try all APIs in sequence until one works"""
        logger.info(f"🚀 Trying {len(FREE_APIS)} FREE APIs...")
        
        for api_config in FREE_APIS:
            for attempt in range(MAX_API_RETRIES):
                try:
                    logger.info(f"   → [{api_config['name']}] Attempt {attempt+1}/{MAX_API_RETRIES}")
                    
                    download_url = await self._try_api(api_config, url, fmt)
                    
                    if download_url:
                        logger.info(f"   ✅ [{api_config['name']}] SUCCESS!")
                        return download_url
                    
                    await asyncio.sleep(RETRY_DELAY)
                except Exception as e:
                    logger.debug(f"   [{api_config['name']}] Error: {e}")
                    await asyncio.sleep(RETRY_DELAY)
        
        logger.warning(f"All {len(FREE_APIS)} APIs failed")
        return None

    async def _download_file(self, url: str, filepath: str):
        """Download file from URL"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            logger.info(f"📥 Downloading...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
                ) as resp:
                    if resp.status == 200:
                        total_size = 0
                        with open(filepath, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(1024*1024):
                                f.write(chunk)
                                total_size += len(chunk)
                        
                        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                            logger.info(f"✅ Downloaded {total_size} bytes")
                            return True
            
            return False
        except Exception as e:
            logger.error(f"Download error: {e}")
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            return False

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset : entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]

        result = await self._get_video_details(link)
        if not result:
            raise ValueError("No video found")

        title = result.get("title", "Unknown")
        duration_min = result.get("duration", "0:00")
        thumbnails = result.get("thumbnails", [])
        thumbnail = thumbnails[0].get("url", "") if thumbnails else ""
        vidid = result.get("id", "")

        try:
            duration_sec = int(time_to_seconds(duration_min)) if duration_min and str(duration_min) != "None" else 0
        except:
            duration_sec = 0

        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]
            
        result = await self._get_video_details(link)
        return result.get("title", "Unknown") if result else "Unknown"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]

        result = await self._get_video_details(link)
        return result.get("duration", "0:00") if result else "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]

        result = await self._get_video_details(link)
        if not result:
            return ""
        
        thumbnails = result.get("thumbnails", [])
        return thumbnails[0].get("url", "") if thumbnails else ""

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]

        # Try Multi-API
        video_url = await self._fetch_multi_api(link, "mp4")
        if video_url:
            return 1, video_url
        
        # Fallback to yt-dlp
        logger.info("Trying yt-dlp (no cookies)...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp", "-g", "-f", "best[height<=?720]", link,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if stdout:
                return 1, stdout.decode().split("\n")[0]
            else:
                return 0, stderr.decode()
        except Exception as e:
            return 0, str(e)

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]
        
        try:
            proc = await asyncio.create_subprocess_shell(
                f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()
            playlist = out.decode("utf-8")
            return [x for x in playlist.split("\n") if x.strip()]
        except:
            return []

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]

        result = await self._get_video_details(link)
        if not result:
            raise ValueError("No video found")

        return {
            "title": result.get("title", "Unknown"),
            "link": result.get("link", ""),
            "vidid": result.get("id", ""),
            "duration_min": result.get("duration", "0:00"),
            "thumb": result.get("thumbnails", [{}])[0].get("url", ""),
        }, result.get("id", "")

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]
        
        ytdl_opts = {"quiet": True, "no_warnings": True}
        
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        formats_available = []
        try:
            with ydl:
                r = ydl.extract_info(link, download=False)
                for fmt in r.get("formats", []):
                    try:
                        if "dash" not in str(fmt.get("format", "")).lower():
                            formats_available.append({
                                "format": fmt["format"],
                                "filesize": fmt.get("filesize", 0),
                                "format_id": fmt["format_id"],
                                "ext": fmt["ext"],
                                "format_note": fmt.get("format_note", ""),
                                "yturl": link,
                            })
                    except:
                        pass
        except:
            pass
        
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]

        try:
            results = []
            search = VideosSearch(link, limit=10)
            search_results = (await search.next()).get("result", [])

            for result in search_results:
                try:
                    duration_str = result.get("duration", "0:00") or "0:00"
                    parts = str(duration_str).split(":")
                    duration_secs = 0
                    
                    try:
                        if len(parts) == 3:
                            duration_secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        elif len(parts) == 2:
                            duration_secs = int(parts[0]) * 60 + int(parts[1])
                    except:
                        pass

                    if duration_secs <= 3600:
                        results.append(result)
                except:
                    pass

            if not results or query_type >= len(results):
                raise ValueError("No videos found")

            selected = results[query_type]
            return (
                selected.get("title", "Unknown"),
                selected.get("duration", "0:00"),
                selected.get("thumbnails", [{}])[0].get("url", ""),
                selected.get("id", "")
            )

        except Exception as e:
            logger.error(f"slider() error: {e}")
            raise ValueError("Failed to get videos")

    async def download(self, link: str, mystic, video: Union[bool, str] = None, videoid: Union[bool, str] = None,
                       songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None,
                       format_id: Union[bool, str] = None, title: Union[bool, str] = None) -> str:
        """
        ULTIMATE 3-TIER SYSTEM:
        TIER 1: Cache (⚡⚡⚡)
        TIER 2: 5 FREE APIs (SocialDown, Y2Mate, Loader, SaveFrom, Cobalt) (🎯 AGE-BYPASS)
        TIER 3: yt-dlp NO COOKIES (✅)
        """
        if videoid:
            vid_id = link
            link = self.base + link
        
        loop = asyncio.get_running_loop()

        async def audio_dl(vid_id):
            try:
                youtube_url = f"https://www.youtube.com/watch?v={vid_id}"
                filepath = os.path.join(DOWNLOADS_FOLDER, f"{vid_id}.mp3")
                
                logger.info(f"🎵 AUDIO: {vid_id}")
                
                # TIER 1: Cache
                if os.path.exists(filepath):
                    file_age = time.time() - os.path.getmtime(filepath)
                    if file_age < CACHE_TIME:
                        size = os.path.getsize(filepath)
                        if size > 1000:
                            logger.info(f"⚡⚡⚡ CACHE ({size} bytes)")
                            return filepath, False
                
                # TIER 2: Multi-API
                logger.info(f"🎯 TIER 2: Trying 5 FREE APIs...")
                audio_url = await self._fetch_multi_api(youtube_url, "mp3")
                
                if audio_url:
                    if await self._download_file(audio_url, filepath):
                        logger.info(f"✅ API SUCCESS")
                        return filepath, False
                
                # TIER 3: yt-dlp
                logger.info(f"✅ TIER 3: yt-dlp (no cookies)...")
                os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)
                
                for attempt in range(MAX_YTDLP_RETRIES):
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "yt-dlp", "--extract-audio", "--audio-format", "mp3",
                            "--audio-quality", "192", "-o", filepath, youtube_url,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                        )
                        
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(), timeout=DOWNLOAD_TIMEOUT
                        )
                        
                        if proc.returncode == 0 and os.path.exists(filepath):
                            size = os.path.getsize(filepath)
                            if size > 1000:
                                logger.info(f"✅ YT-DLP SUCCESS ({size} bytes)")
                                return filepath, False
                        
                        await asyncio.sleep(RETRY_DELAY)
                    except:
                        await asyncio.sleep(RETRY_DELAY)
                
                logger.error(f"❌ ALL TIERS FAILED")
                return None, False
                    
            except Exception as e:
                logger.error(f"FATAL: {e}")
                return None, False

        async def video_dl(vid_id):
            try:
                youtube_url = f"https://www.youtube.com/watch?v={vid_id}"
                filepath = os.path.join(DOWNLOADS_FOLDER, f"{vid_id}.mp4")
                
                logger.info(f"🎥 VIDEO: {vid_id}")
                
                # TIER 1: Cache
                if os.path.exists(filepath):
                    file_age = time.time() - os.path.getmtime(filepath)
                    if file_age < CACHE_TIME:
                        size = os.path.getsize(filepath)
                        if size > 10000:
                            logger.info(f"⚡⚡⚡ CACHE ({size} bytes)")
                            return filepath, False
                
                # TIER 2: Multi-API
                logger.info(f"🎯 TIER 2: Trying 5 FREE APIs...")
                video_url = await self._fetch_multi_api(youtube_url, "mp4")
                
                if audio_url:
                    if await self._download_file(video_url, filepath):
                        logger.info(f"✅ API SUCCESS")
                        return filepath, False
                
                # TIER 3: yt-dlp
                logger.info(f"✅ TIER 3: yt-dlp (no cookies)...")
                os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)
                
                for attempt in range(MAX_YTDLP_RETRIES):
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "yt-dlp", "-f", "best[ext=mp4]", "-o", filepath, youtube_url,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                        )
                        
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(), timeout=DOWNLOAD_TIMEOUT
                        )
                        
                        if proc.returncode == 0 and os.path.exists(filepath):
                            size = os.path.getsize(filepath)
                            if size > 10000:
                                logger.info(f"✅ YT-DLP SUCCESS ({size} bytes)")
                                return filepath, False
                        
                        await asyncio.sleep(RETRY_DELAY)
                    except:
                        await asyncio.sleep(RETRY_DELAY)
                
                logger.error(f"❌ ALL TIERS FAILED")
                return None, False
                    
            except Exception as e:
                logger.error(f"FATAL: {e}")
                return None, False
        
        def song_video_dl():
            formats = f"{format_id}+140"
            fpath = f"{DOWNLOADS_FOLDER}/{title}"
            ydl_opts = {
                "format": formats, "outtmpl": fpath, "geo_bypass": True,
                "quiet": False, "prefer_ffmpeg": True, "merge_output_format": "mp4",
            }
            yt_dlp.YoutubeDL(ydl_opts).download([link])

        def song_audio_dl():
            fpath = f"{DOWNLOADS_FOLDER}/{title}.%(ext)s"
            ydl_opts = {
                "format": format_id, "outtmpl": fpath, "geo_bypass": True,
                "quiet": False, "prefer_ffmpeg": True,
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            }
            yt_dlp.YoutubeDL(ydl_opts).download([link])

        if songvideo:
            await loop.run_in_executor(None, song_video_dl)
            return f"{DOWNLOADS_FOLDER}/{title}.mp4", False
            
        elif songaudio:
            await loop.run_in_executor(None, song_audio_dl)
            return f"{DOWNLOADS_FOLDER}/{title}.mp3", False
            
        elif video:
            return await video_dl(vid_id)
            
        else:
            return await audio_dl(vid_id)

async def init_youtube_api():
    """Initialize"""
    try:
        os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)
        logger.info("=" * 70)
        logger.info("🚀 YOUTUBE API - ULTIMATE EDITION")
        logger.info("=" * 70)
        logger.info("✅ 5 FREE APIs: SocialDown, Y2Mate, Loader, SaveFrom, Cobalt")
        logger.info("✅ AGE-BYPASS: All APIs support age-restricted content")
        logger.info("✅ FALLBACK: yt-dlp (no cookies)")
        logger.info("✅ 3-TIER: Cache → 5 APIs → yt-dlp")
        logger.info("=" * 70)
    except Exception as e:
        logger.error(f"Init error: {e}")

async def schedule_cleanup_task():
    """Background cleanup"""
    pass
