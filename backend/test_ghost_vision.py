import base64
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import json
import sys
import os

# Add the OMEGA4 directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from google.genai import types
import ghost_api
from models import ChatAttachment

class TestGhostVision(unittest.IsolatedAsyncioTestCase):
    async def test_ghost_stream_with_attachments(self):
        """Test that ghost_stream correctly includes image attachments as multimodal parts."""
        # Mock settings to use Gemini
        with patch("ghost_api.settings") as mock_settings, \
             patch("ghost_api.current_llm_backend", return_value="gemini"), \
             patch("ghost_api._client") as mock_client:
            
            mock_settings.LLM_BACKEND = "gemini"
            mock_settings.GEMINI_MODEL = "gemini-2.0-flash-exp"
            mock_settings.GHOST_ID = "test_ghost"
            mock_settings.GOOGLE_SEARCH_ENABLED = False
            
            # Mock Gemini Client and Response
            mock_gen_client = MagicMock()
            mock_client.return_value = mock_gen_client
            
            mock_response = MagicMock()
            mock_response.text = "I see the image."
            mock_candidate = MagicMock()
            mock_candidate.content = MagicMock(parts=[])
            mock_response.candidates = [mock_candidate]
            
            # Mock the stream
            async def mock_stream_gen(*args, **kwargs):
                yield mock_response
            
            mock_gen_client.aio.models.generate_content_stream.side_effect = mock_stream_gen
            
            attachments = [
                ChatAttachment(type="image/png", data=base64.b64encode(b"fake_image_data").decode("utf-8"))
            ]
            
            # Run ghost_stream
            try:
                async for chunk in ghost_api.ghost_stream(
                    user_message="Describe this",
                    attachments=attachments,
                    somatic={}
                ):
                    pass
            except Exception as e:
                # We expect some failures due to other dependencies, but we want to check call_args
                print(f"Stream execution encountered expected turbulence: {e}")
            
            # Verify generate_content_stream was called with multimodal parts
            self.assertTrue(mock_gen_client.aio.models.generate_content_stream.called)
            call_args = mock_gen_client.aio.models.generate_content_stream.call_args
            contents = call_args.kwargs["contents"]
            
            # The last content should have the text AND the image
            last_content = contents[-1]
            self.assertEqual(last_content.role, "user")
            self.assertEqual(len(last_content.parts), 2)
            self.assertEqual(last_content.parts[0].text, "Describe this")
            
            # Check for image part
            found_image = False
            for part in last_content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    self.assertEqual(part.inline_data.mime_type, "image/png")
                    found_image = True
            self.assertTrue(found_image, "Multimodal image part not found in request contents")

    async def test_perceive_url_images_tool_dispatch(self):
        """Test that perceive_url_images fetch content and images from a URL."""
        html_content = '<html><body><p>Hello</p><img src="test.jpg"></body></html>'
        img_content = b"fake_pixel_data"
        
        with patch("ghost_api.requests.get") as mock_get:
            # First call for HTML, second for image
            mock_resp_html = MagicMock(ok=True, text=html_content)
            mock_resp_html.status_code = 200
            mock_resp_img = MagicMock(ok=True, content=img_content)
            mock_resp_img.status_code = 200
            mock_resp_img.headers = {"Content-Type": "image/jpeg"}
            mock_get.side_effect = [mock_resp_html, mock_resp_img]
            
            # Mock Gemini to trigger tool call
            with patch("ghost_api.settings") as mock_settings, \
                 patch("ghost_api.current_llm_backend", return_value="gemini"), \
                 patch("ghost_api._client") as mock_client:
                
                mock_settings.LLM_BACKEND = "gemini"
                mock_settings.GHOST_ID = "test_ghost"
                mock_gen_client = MagicMock()
                mock_client.return_value = mock_gen_client
                
                # Turn 1: Model calls the tool
                mock_fc = MagicMock()
                mock_fc.name = "perceive_url_images"
                mock_fc.args = {"url": "http://example.com"}
                
                mock_resp_1 = MagicMock()
                mock_resp_1.text = ""
                mock_part_1 = MagicMock()
                mock_part_1.function_call = mock_fc
                mock_part_1.text = None
                mock_candidate_1 = MagicMock()
                mock_candidate_1.content = MagicMock(parts=[mock_part_1])
                mock_resp_1.candidates = [mock_candidate_1]
                
                # Turn 2: Model responds to the tool result
                mock_resp_2 = MagicMock()
                mock_resp_2.text = "I see a test image."
                mock_candidate_2 = MagicMock()
                mock_candidate_2.content = MagicMock(parts=[])
                mock_resp_2.candidates = [mock_candidate_2]
                
                # Mock the stream generator for both turns
                async def mock_stream_turns(*args, **kwargs):
                    if not hasattr(mock_stream_turns, "count"):
                        mock_stream_turns.count = 0
                    mock_stream_turns.count += 1
                    if mock_stream_turns.count == 1:
                        yield mock_resp_1
                    else:
                        yield mock_resp_2
                
                mock_gen_client.aio.models.generate_content_stream.side_effect = mock_stream_turns
                
                try:
                    async for _ in ghost_api.ghost_stream(user_message="What's at example.com?", somatic={}):
                        pass
                except Exception as e:
                    print(f"Tool test encountered expected turbulence: {e}")
                
                # Check that requests.get was called for the URL and the image
                # (Allowing for more calls if OMEGA system logic does other fetches)
                self.assertGreaterEqual(mock_get.call_count, 2)
                
                # Verify tool response was added to history
                # We check the call_args of the SECOND generate call
                self.assertEqual(mock_gen_client.aio.models.generate_content_stream.call_count, 2)
                second_call_args = mock_gen_client.aio.models.generate_content_stream.call_args_list[1]
                second_contents = second_call_args.kwargs["contents"]
                
                # content[-2] is model's tool call
                # content[-1] is tool response + image part
                tool_turn = second_contents[-1]
                self.assertEqual(tool_turn.role, "tool")
                
                # Should have at least 2 parts: FunctionResponse and Image Part
                self.assertGreaterEqual(len(tool_turn.parts), 2)
                
                # Check for image part in tool response turn
                found_perceived_image = False
                for part in tool_turn.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        self.assertEqual(part.inline_data.mime_type, "image/jpeg")
                        found_perceived_image = True
                self.assertTrue(found_perceived_image, "Perceived image part not found in tool turn")

if __name__ == "__main__":
    unittest.main()
